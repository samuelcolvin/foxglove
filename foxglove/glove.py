import asyncio

import httpx
from buildpg.asyncpg import BuildPgPool

from .db import create_pg_pool
from .settings import BaseSettings

__all__ = ('glove',)


class Glove:
    settings: BaseSettings
    pg: BuildPgPool
    http: httpx.AsyncClient

    async def startup(self):
        self.pg = await create_pg_pool(self.settings)
        self.http = httpx.AsyncClient(timeout=self.settings.http_client_timeout)

    async def shutdown(self):
        await asyncio.gather(self.pg.close(), self.http.aclose())


glove = Glove()
