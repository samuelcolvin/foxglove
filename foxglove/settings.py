import os
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern
from urllib.parse import urlparse

from pydantic import BaseSettings as PydanticBaseSettings, validator
from starlette.applications import Starlette
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


__all__ = ('BaseSettings',)


class BaseSettings(PydanticBaseSettings):
    dev_mode: bool = False
    test_mode: bool = False
    release: Optional[str] = None
    environment: str = 'dev'
    sentry_dsn: Optional[str] = None
    log_level: str = 'INFO'
    origin: str = None

    bcrypt_rounds: int = 14

    asgi_path: str = 'foxglove.asgi:app'
    # TODO src here should be replaced with '.main:app' then prefixed with the name of the directory settings is in
    app: str = 'src.main:app'
    web_workers: Optional[int] = None

    worker_func: Optional[str] = None

    patch_paths: List[str] = ['src.patches']

    sql_path: Path = 'models.sql'
    pg_dsn: Optional[str] = pg_dsn_default
    # eg. the db already exists on heroku and never has to be created
    pg_db_exists = False
    pg_pool_min_size: int = 10
    pg_pool_max_size: int = 10

    redis_settings: Optional[RedisSettings] = redis_settings_default
    port: int = 8000

    # secrets.token_hex() is used to avoid a public default value ever being used in production
    secret_key: str = secrets.token_hex()
    cookie_name: str = 'foxglove'

    locale: Optional[str] = None

    http_client_timeout = 10

    csrf_ignore_paths: List[Pattern] = []
    csrf_upload_paths: List[Pattern] = []
    csrf_cross_origin_paths: List[Pattern] = []
    cross_origin_origins: List[Pattern] = []

    recaptcha_url = 'https://www.google.com/recaptcha/api/siteverify'
    # this is the recaptcha test key, you'll need to change it for production, see
    # https://developers.google.com/recaptcha/docs/faq#id-like-to-run-automated-tests-with-recaptcha-what-should-i-do
    recaptcha_secret = '6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe'

    @property
    def sql(self):
        return self.sql_path.read_text()

    def create_app(self) -> Starlette:
        return import_from_string(self.app)

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
        return RedisSettings.from_dsn(v)

    @validator('pg_db_exists', always=True)
    def pg_db_exists_heroku(cls, v: bool) -> bool:
        """
        pg_db_exists should be true by default on heroku, but not if PG_DB_EXISTS is set to false.
        """
        if v or any('PG_DB_EXISTS' == k.upper() for k in os.environ):
            return v
        else:
            return 'DYNO' in os.environ or 'HEROKU_SLUG_COMMIT' in os.environ

    @validator('environment', always=True)
    def set_environment(cls, v: str, values: Dict[str, Any]) -> str:
        if values.get('dev_mode'):
            return 'dev'
        return v

    @validator('sentry_dsn', always=True)
    def set_sentry_dsn(cls, sentry_dsn: Optional[str]) -> Optional[str]:
        if sentry_dsn in ('', '-'):
            # thus setting an environment variable of "-" means no sentry
            return None
        else:
            return sentry_dsn

    @validator('release', always=True)
    def set_release(cls, release: Optional[str]) -> Optional[str]:
        if release:
            return release[:7]
        else:
            return release

    class Config:
        fields = {
            'pg_dsn': {'env': 'DATABASE_URL'},
            'redis_settings': {'env': ['REDISCLOUD_URL', 'REDIS_URL']},
            'dev_mode': {'env': ['foxglove_dev_mode']},
            'environment': {'env': ['ENV', 'ENVIRONMENT']},
            'release': {'env': ['COMMIT', 'RELEASE', 'HEROKU_SLUG_COMMIT']},
        }
