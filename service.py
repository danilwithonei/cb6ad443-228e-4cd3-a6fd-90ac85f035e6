import os
import logging
from dynaconf import settings
from pathlib import Path

from factories import create_rabbit_connection, create_s3_connection
from connections import RabbitMQConnection, BlockingChannel, S3Connection
from face_swapper import FaceSwapper
from models import InputMessage, OutputMessage


INPUT_QUEUE = "input_queue"
OUTPUT_QUEUE = "output_queue"

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, "INFO"), format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("worker")


class Service:
    def __init__(
        self,
        rabbit_mq_conn: RabbitMQConnection | None = None,
        s3_client: S3Connection | None = None,
    ):
        self.rabbit_mq_conn = rabbit_mq_conn
        self.s3_client = s3_client
        self.f_swapper = FaceSwapper()

    def upload_result_video(self, message_id: str, result_video_path: str) -> str:
        s3_result_path = os.path.join(
            message_id,
            os.path.basename(result_video_path),
        )
        self.s3_client.client.upload_file(result_video_path, self.s3_client.bucket, s3_result_path)
        return s3_result_path

    def process_message(self, ch: BlockingChannel, method, properties, body):
        input_message = InputMessage.model_validate_json(body)

        def update_status(status: str, metadata: dict | None = None):
            out_message = OutputMessage(id=input_message.id, status=status, metadata=metadata or {})
            try:
                ch.basic_publish(exchange="", routing_key=OUTPUT_QUEUE, body=out_message.model_dump_json())
                logger.debug(f"Status update sent for ID {input_message.id}: {metadata}")
            except Exception as e:
                logger.error(f"Failed to send status update for ID {input_message.id}: {str(e)}")

        try:
            logger.info(f"Processing request ID: {input_message.id}")

            _o = str(Path(input_message.payload.img_target_path).parent)
            local_path_to_video = self.s3_client.download_file(
                input_message.payload.video_source_path,
                _o,
            )
            local_path_to_image = self.s3_client.download_file(
                input_message.payload.img_target_path,
                _o,
            )

            output_video_path = os.path.join(_o, "result.mp4")

            output = self.f_swapper.swap_faces(
                source_video=local_path_to_video,
                target_face_img=local_path_to_image,
                output_video=output_video_path,
                update_status_func=update_status,
            )

            s3_result_path = self.s3_client.upload_file(
                local_file_path=output_video_path,
                s3_file_path=_o,
                delete_local_file_path=True,
            )

            update_status("done", {"result_path": s3_result_path})
            ch.basic_ack(delivery_tag=method.delivery_tag)
            logger.info(f"Status sent for ID: {input_message.id}")

        except Exception as e:
            logger.exception(f"Processing failed: {str(e)}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        pass

    def start(self):
        logger.info("Starting message consumer")
        with self.rabbit_mq_conn as channel:
            channel.queue_declare(queue=INPUT_QUEUE, durable=True)
            channel.queue_declare(queue=OUTPUT_QUEUE, durable=True)
            logger.info("Queues declared successfully")

            channel.basic_consume(queue=INPUT_QUEUE, on_message_callback=self.process_message)
            logger.info("Waiting for messages.")
            channel.start_consuming()
        pass


def main():

    os.makedirs("./results", exist_ok=True)
    rabbit_connection = create_rabbit_connection()
    s3_client = create_s3_connection()

    service = Service(rabbit_mq_conn=rabbit_connection, s3_client=s3_client)
    service.start()


if __name__ == "__main__":
    main()
