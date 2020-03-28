from pathlib import Path
from typing import List, Optional, Pattern
from urllib.parse import urlparse

from pydantic import BaseSettings as PydanticBaseSettings, validator
from starlette.routing import Route
from uvicorn.importer import import_from_string

try:
    from arq.connections import RedisSettings

    redis_settings_default = 'redis://localhost:6379'
except ImportError:
    redis_settings_default = None

    class RedisSettings:
        """
        Mock arq.RedisSettings to satisfy pydantic if arq isn't installed
        """

        def __init__(self, *args, **kwargs):
            raise RuntimeError('arq not installed')


try:
    from buildpg import asyncpg  # noqa
except ImportError:
    pg_dsn_default = None
else:
    pg_dsn_default = 'postgres://postgres@localhost:5432/app'


class BaseSettings(PydanticBaseSettings):
    dev_mode: bool = False
    asgi_path: str = 'foxglove.asgi:app'
    routes: Optional[str] = None
    web_workers: Optional[int] = None

    worker_func: Optional[str] = None

    patch_paths: List[str] = []

    sql_path: Path = 'models.sql'
    template_dir: Optional[Path] = 'templates'
    pg_dsn: Optional[str] = pg_dsn_default
    # eg. the db already exists on heroku and never has to be created
    pg_db_exists = False
    pg_pool_min_size: int = 10
    pg_pool_max_size: int = 10

    redis_settings: Optional[RedisSettings] = redis_settings_default
    port: int = 8000

    locale: Optional[str] = None

    http_client_timeout = 10

    csrf_ignore_paths: List[Pattern] = []
    csrf_upload_paths: List[Pattern] = []
    csrf_cross_origin_paths: List[Pattern] = []
    cross_origin_origins: List[Pattern] = []

    grecaptcha_url = 'https://www.google.com/recaptcha/api/siteverify'

    # this is the test key from https://developers.google.com/recaptcha/docs/faq, or
    # https://developers.google.com/recaptcha/docs/faq#id-like-to-run-automated-tests-with-recaptcha-what-should-i-do
    # you'll need to change it for production
    grecaptcha_secret = '6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe'

    @property
    def sql(self):
        return self.sql_path.read_text()

    def get_routes(self) -> List[Route]:
        routes = self.routes or f'{self.__module__}:routes'
        return import_from_string(routes)

    @property
    def _pg_dsn_parsed(self):
        return urlparse(self.pg_dsn)

    @property
    def pg_name(self):
        return self._pg_dsn_parsed.path.lstrip('/')

    @property
    def pg_host(self):
        return self._pg_dsn_parsed.hostname

    @property
    def pg_port(self):
        return self._pg_dsn_parsed.port

    @validator('redis_settings', always=True, pre=True)
    def parse_redis_settings(cls, v):
        if v is None:
            return

        if RedisSettings.__module__ != 'arq.connections':
            raise RuntimeError(f'arq must be installed to use redis, redis_settings set to {v!r}')
        conf = urlparse(v)
        return RedisSettings(
            host=conf.hostname, port=conf.port, password=conf.password, database=int((conf.path or '0').strip('/'))
        )

    class Config:
        fields = {
            'pg_dsn': {'env': 'DATABASE_URL'},
            'redis_settings': {'env': ['REDISCLOUD_URL', 'REDIS_URL']},
            'dev_mode': {'env': ['foxglove_dev_mode']},
        }
