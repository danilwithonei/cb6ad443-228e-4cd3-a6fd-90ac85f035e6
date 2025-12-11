import os
import logging
from dynaconf import settings

from factories import create_rabbit_connection
from connections import RabbitMQConnection, BlockingChannel
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
        rabbit_mq_conn: RabbitMQConnection = None,
    ):
        self.rabbit_mq_conn = rabbit_mq_conn
        self.f_swapper = FaceSwapper()

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
            output_video = os.path.join("results", input_message.id + ".mp4")

            output = self.f_swapper.swap_faces(
                source_video=input_message.video_path,
                target_face_img=input_message.image_path,
                output_video=output_video,
                update_status_func=update_status,
            )

            update_status("done")
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

    service = Service(
        rabbit_mq_conn=rabbit_connection,
    )
    service.start()


if __name__ == "__main__":
    main()
