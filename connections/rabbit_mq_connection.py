from pika import ConnectionParameters, PlainCredentials, BlockingConnection
from pika.adapters.blocking_connection import BlockingChannel


class RabbitMQConnection:
    def __init__(self, host: str, port: int, username: str, password: str):
        self._config: dict = {
            "host": host,
            "port": port,
            "credentials": PlainCredentials(username, password),
            "connection_attempts": 3,
            "retry_delay": 2,
        }
        self._connection: None | BlockingConnection = None

    def __enter__(self) -> BlockingChannel:
        return self.get_channel()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_channel(self) -> BlockingChannel:
        if not self._connection or self._connection.is_closed:
            self._connection = BlockingConnection(ConnectionParameters(**self._config))
        return self._connection.channel()

    def close(self):
        if self._connection and self._connection.is_open:
            self._connection.close()
