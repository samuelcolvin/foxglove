import logging

import pytest

from foxglove.db import prepare_database
from foxglove.redis import async_flush_redis, flush_redis
from foxglove.settings import BaseSettings
from tests.conftest import ConnContext

pytestmark = pytest.mark.asyncio


@pytest.mark.filterwarnings('ignore::DeprecationWarning')
async def test_prepare_database(db_conn_global, alt_settings: BaseSettings):
    await db_conn_global.execute(f'drop database if exists {alt_settings.pg_name}')

    assert (
        await db_conn_global.fetchval('SELECT true FROM pg_catalog.pg_database where datname=$1', alt_settings.pg_name)
        is None
    )

    await prepare_database(alt_settings, True)

    assert (
        await db_conn_global.fetchval('SELECT true FROM pg_catalog.pg_database where datname=$1', alt_settings.pg_name)
        is True
    )


async def test_prepare_database_replace(db_conn_global, alt_settings: BaseSettings):
    await prepare_database(alt_settings, True)

    async with ConnContext(alt_settings.pg_dsn) as conn:
        await conn.execute("insert into organisations (name) values ('foobar')")
        assert await conn.fetchval('select count(*) from organisations') == 1

    await prepare_database(alt_settings, True)

    async with ConnContext(alt_settings.pg_dsn) as conn:
        assert await conn.fetchval('select count(*) from organisations') == 0


async def test_prepare_database_keep(db_conn_global, alt_settings: BaseSettings):
    await prepare_database(alt_settings, True)

    async with ConnContext(alt_settings.pg_dsn) as conn:
        await conn.execute("insert into organisations (name) values ('foobar')")
        assert await conn.fetchval('select count(*) from organisations') == 1

    await prepare_database(alt_settings, False)

    async with ConnContext(alt_settings.pg_dsn) as conn:
        assert await conn.fetchval('select count(*) from organisations') == 1


def test_flush_redis_yes(settings, caplog, mocker):
    caplog.set_level(logging.INFO)
    mocker.patch('foxglove.redis.input', return_value='y')
    flush_redis(settings)
    assert caplog.record_tuples == [
        ('foxglove.redis', logging.INFO, 'resetting database...'),
        ('foxglove.redis', logging.INFO, 'done.'),
    ]


def test_flush_redis_no(settings, caplog, mocker):
    caplog.set_level(logging.INFO)
    mocker.patch('foxglove.redis.input', return_value='n')
    flush_redis(settings)
    assert caplog.record_tuples == [('foxglove.redis', logging.INFO, 'cancelling')]


async def test_async_flush_redis(settings, glove):
    await glove.redis.set('foo', '1')
    await glove.redis.set('bar', '2')
    assert len(await glove.redis.keys('*')) == 2
    await async_flush_redis(settings)
    assert len(await glove.redis.keys('*')) == 0
