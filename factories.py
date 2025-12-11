from dynaconf import settings
from connections import RedisClient, RabbitMQConnection


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
