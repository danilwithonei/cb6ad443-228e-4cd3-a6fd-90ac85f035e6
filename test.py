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
                    {"id": "12378998776", "video_path": "1/video.mp4", "image_path": "1/image.png"},
                ).encode()
            ),
            routing_key="input_queue",
        )
        print("sended")


if __name__ == "__main__":
    asyncio.run(main())
