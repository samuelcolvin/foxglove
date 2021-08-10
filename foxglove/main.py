import asyncio
import os
from typing import Literal

import arq
import httpx
from buildpg.asyncpg import BuildPgPool
from pydantic.env_settings import BaseSettings as PydanticBaseSettings
from uvicorn.importer import ImportFromStringError, import_from_string

from .db import create_pg_pool
from .settings import BaseSettings

__all__ = ('glove',)


class Glove:
    _settings: BaseSettings
    _http: httpx.AsyncClient
    pg: BuildPgPool
    redis: arq.ArqRedis

    async def startup(self, *, run_migrations: Literal[True, False, 'unless-test-mode'] = 'unless-test-mode') -> None:
        from .logs import setup_sentry

        setup_sentry()

        if run_migrations == 'unless-test-mode':
            run_migrations = not self.settings.test_mode

        if not hasattr(self, 'pg'):
            self.pg = await create_pg_pool(self.settings, run_migrations=run_migrations)
        if not hasattr(self, 'redis') and self.settings.redis_settings:
            self.redis = await arq.create_pool(self.settings.redis_settings)

    def context(self) -> 'GloveContext':
        return GloveContext(self)

    async def shutdown(self) -> None:
        coros = []
        if pg := getattr(self, 'pg', None):
            coros.append(pg.close())
        if http := getattr(self, '_http', None):
            coros.append(http.aclose())
        if redis := getattr(self, 'redis', None):
            redis.close()
            coros.append(redis.wait_closed())
        await asyncio.gather(*coros)
        for prop in 'pg', '_http', 'redis':
            if hasattr(self, prop):
                delattr(self, prop)

    @property
    def http(self) -> httpx.AsyncClient:
        http = getattr(self, '_http', None)
        if http is None:
            http = self._http = httpx.AsyncClient(timeout=self.settings.http_client_timeout)
        return http

    @property
    def settings(self) -> BaseSettings:
        settings = getattr(self, '_settings', None)
        if settings is None:
            settings_path = os.environ['foxglove_settings_path']
            try:
                settings_cls = import_from_string(settings_path)
            except ImportFromStringError as exc:
                raise ImportError(f'unable to import "{settings_path}", {exc.__class__.__name__}: {exc}')

            if not isinstance(settings_cls, type) or not issubclass(settings_cls, PydanticBaseSettings):
                raise ImportError(f'settings "{settings_cls}" (from "{settings_path}"), is not a valid Settings class')

            settings = self._settings = settings_cls()
        return settings


class GloveContext:
    def __init__(self, g: Glove):
        self._glove = g

    async def __aenter__(self) -> None:
        await self._glove.startup()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._glove.shutdown()


glove = Glove()
