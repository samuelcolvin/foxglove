import asyncpg
import pytest

from foxglove.db import prepare_database
from foxglove.settings import BaseSettings

pytestmark = pytest.mark.asyncio


async def test_prepare_database(db_conn_global, settings: BaseSettings):
    await db_conn_global.execute(f'drop database if exists {settings.pg_name}')

    assert (
        await db_conn_global.fetchval('SELECT true FROM pg_catalog.pg_database where datname=$1', settings.pg_name)
        is None
    )

    await prepare_database(settings, True)

    assert (
        await db_conn_global.fetchval('SELECT true FROM pg_catalog.pg_database where datname=$1', settings.pg_name)
        is True
    )


class ConnContext:
    def __init__(self, dsn):
        self._dsn = dsn
        self._conn = None

    async def __aenter__(self) -> asyncpg.Connection:
        self._conn = await asyncpg.connect(self._dsn)
        return self._conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._conn.close()


async def test_prepare_database_replace(db_conn_global, settings: BaseSettings):
    await prepare_database(settings, True)

    async with ConnContext(settings.pg_dsn) as conn:
        await conn.execute("insert into organisations (name) values ('foobar')")
        assert await conn.fetchval('select count(*) from organisations') == 1

    await prepare_database(settings, True)

    async with ConnContext(settings.pg_dsn) as conn:
        assert await conn.fetchval('select count(*) from organisations') == 0


async def test_prepare_database_keep(db_conn_global, settings: BaseSettings):
    await prepare_database(settings, True)

    async with ConnContext(settings.pg_dsn) as conn:
        await conn.execute("insert into organisations (name) values ('foobar')")
        assert await conn.fetchval('select count(*) from organisations') == 1

    await prepare_database(settings, False)

    async with ConnContext(settings.pg_dsn) as conn:
        assert await conn.fetchval('select count(*) from organisations') == 1
