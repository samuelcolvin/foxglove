import asyncio
import os

import httpx
from buildpg.asyncpg import BuildPgPool
from uvicorn.importer import import_from_string

from .db import create_pg_pool
from .settings import BaseSettings

__all__ = ('glove',)


class Glove:
    settings: BaseSettings
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

    def init_settings(self) -> BaseSettings:
        if not hasattr(self, 'settings'):
            settings_cls = import_from_string(os.environ['foxglove_settings_path'])
            self.settings: BaseSettings = settings_cls()
        return self.settings


glove = Glove()
