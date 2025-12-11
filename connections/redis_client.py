import redis


class RedisClient:
    def __init__(self, host: str, port: int, password: str, db: int = 0):
        self._config: dict = {
            "host": host,
            "port": port,
            "password": password,
            "db": db,
            "decode_responses": True,
            "socket_timeout": 5,
            "socket_connect_timeout": 5,
            "retry_on_timeout": True,
        }
        self._client: None | redis.Redis = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.Redis(**self._config)
        return self._client

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
