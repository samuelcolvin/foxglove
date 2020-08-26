import asyncio
import os

import httpx
from buildpg.asyncpg import BuildPgPool
from pydantic.env_settings import BaseSettings as PydanticBaseSettings
from uvicorn.importer import ImportFromStringError, import_from_string

from .db import create_pg_pool
from .settings import BaseSettings

__all__ = ('glove',)


class Glove:
    _settings: BaseSettings
    pg: BuildPgPool
    http: httpx.AsyncClient

    async def startup(self):
        if not hasattr(self, 'pg'):
            self.pg = await create_pg_pool(self.settings)
        if not hasattr(self, 'http'):
            self.http = httpx.AsyncClient(timeout=self.settings.http_client_timeout)

    async def shutdown(self):
        await asyncio.gather(self.pg.close(), self.http.aclose())
        del self.pg
        del self.http

    @property
    def settings(self) -> BaseSettings:
        settings = getattr(self, '_settings', None)
        if settings is None:
            settings_path = os.environ['foxglove_settings_path']
            try:
                settings_cls = import_from_string(settings_path)
            except ImportFromStringError as exc:
                raise RuntimeError(f'unable to import "{settings_path}", {exc.__class__.__name__}: {exc}')

            if not isinstance(settings_cls, type) or not issubclass(settings_cls, PydanticBaseSettings):
                raise RuntimeError(f'settings "{settings_cls}" (from "{settings_path}"), is not a valid Settings class')

            settings = self._settings = settings_cls()
        return settings


glove = Glove()
