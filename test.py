import asyncio
import aio_pika
import json
from dynaconf import settings

RABBIT_URL = (
    f"amqp://{settings.RABBITMQ_USER}:{settings.RABBITMQ_PASS}@{settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}/"
)


async def main():
    conn = await aio_pika.connect(RABBIT_URL)
    print("connected")
    async with conn:
        channel = await conn.channel()
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(
                    {
                        "id": "123789987",
                        "payload": {
                            "video_source_path": "deep_fake_files/68ea432f-c55d-4f43-a8f0-b5ef4c228d00/2.mp4",
                            "img_target_path": "deep_fake_files/68ea432f-c55d-4f43-a8f0-b5ef4c228d00/photo_2025-12-12_23-05-34.jpg",
                        },
                        "created_at": "now",
                    },
                ).encode()
            ),
            routing_key="input_queue",
        )
        print("sended")


if __name__ == "__main__":
    asyncio.run(main())
