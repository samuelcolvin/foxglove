import asyncio
import logging
from typing import Optional

from async_timeout import timeout
from asyncpg import PostgresError
from buildpg.asyncpg import BuildPgConnection, connect_b

from ..settings import BaseSettings

__all__ = 'AsyncPgContext', 'lenient_conn'

logger = logging.getLogger('foxglove.db')


class AsyncPgContext:
    def __init__(self, pg_dsn: str):
        self._pg_dsn = pg_dsn
        self._conn: Optional[BuildPgConnection] = None

    async def __aenter__(self) -> BuildPgConnection:
        self._conn = await connect_b(dsn=self._pg_dsn)
        return self._conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._conn:
            await self._conn.close()


async def lenient_conn(settings: BaseSettings, *, with_db: bool = True, sleep: float = 1) -> BuildPgConnection:
    if with_db:
        dsn = settings.pg_dsn
    else:
        dsn, _ = settings.pg_dsn.rsplit('/', 1)

    for retry in range(8, -1, -1):
        try:
            async with timeout(2):
                conn = await connect_b(dsn=dsn)
        except (PostgresError, OSError) as e:
            if retry == 0:
                raise
            else:
                logger.warning('pg temporary connection error "%s", %d retries remaining...', e, retry)
                await asyncio.sleep(sleep)
        else:
            log = logger.debug if retry == 8 else logger.info
            log('pg connection successful, version: %s', await conn.fetchval('SELECT version()'))
            return conn
