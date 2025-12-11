from dynaconf import settings
from connections import RedisClient, RabbitMQConnection, S3Connection


def create_redis_client() -> RedisClient:
    return RedisClient(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
    )


def create_rabbit_connection() -> RabbitMQConnection:
    return RabbitMQConnection(
        host=settings.RABBITMQ_HOST,
        port=settings.RABBITMQ_PORT,
        username=settings.RABBITMQ_USER,
        password=settings.RABBITMQ_PASS,
    )


def create_s3_connection() -> S3Connection:
    return S3Connection(endpoint_url=settings.ENDPOINT_URL, bucket=settings.BUCKET)
