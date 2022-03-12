import logging

from buildpg.asyncpg import BuildPgConnection
from dirty_equals import IsNow, IsPositiveInt

from foxglove.db import prepare_database
from foxglove.db.utils import AsyncPgContext
from foxglove.redis import async_flush_redis, flush_redis
from foxglove.settings import BaseSettings
from tests.conftest import ConnContext


async def test_prepare_database(db_conn_global: BuildPgConnection, alt_settings: BaseSettings, caplog):
    await db_conn_global.execute(f'drop database if exists {alt_settings.pg_name}')
    alt_settings.pg_migrations = True

    assert (
        await db_conn_global.fetchval('SELECT true FROM pg_catalog.pg_database where datname=$1', alt_settings.pg_name)
        is None
    )

    with caplog.at_level(logging.INFO, 'foxglove.db'):
        assert await prepare_database(alt_settings, True) is True

    assert (
        await db_conn_global.fetchval('SELECT true FROM pg_catalog.pg_database where datname=$1', alt_settings.pg_name)
        is True
    )

    with caplog.at_level(logging.INFO, 'foxglove'):
        assert await prepare_database(alt_settings, False) is False

    async with AsyncPgContext(alt_settings.pg_dsn) as conn:
        assert await conn.fetchval('select count(*) from migrations') == 1
        migrations = dict(await conn.fetchrow('select * from migrations'))

    assert migrations == {
        'id': IsPositiveInt,
        'ref': 'run_full_name',
        'sql_section': (
            'full_name::\n'
            'create or replace function full_name(u users) returns varchar as $$\n'
            '  begin\n'
            "    return coalesce(u.first_name || ' ' || u.last_name, u.first_name, u.last_name);\n"
            '  end;\n'
            '$$ language plpgsql;'
        ),
        'ts': IsNow(tz='utc'),
        'fake': True,
    }

    assert caplog.messages == [
        'database successfully setup ✓',
        'migrations table created',
        'checking 1 migration patches...',
        'faked migration run_full_name',
        '1 migration patches faked, 0 already up to date ✓',
        'database already exists ✓',
        'checking 1 migration patches...',
        'all 1 migrations already up to date ✓',
    ]
    alt_settings.pg_migrations = False


async def test_prepare_database_replace(alt_settings: BaseSettings):
    await prepare_database(alt_settings, True)

    async with ConnContext(alt_settings.pg_dsn) as conn:
        await conn.execute("insert into organisations (name) values ('foobar')")
        assert await conn.fetchval('select count(*) from organisations') == 1

    assert await prepare_database(alt_settings, True) is True

    async with ConnContext(alt_settings.pg_dsn) as conn:
        assert await conn.fetchval('select count(*) from organisations') == 0


async def test_prepare_database_keep(db_conn_global, alt_settings: BaseSettings):
    await prepare_database(alt_settings, True)

    async with ConnContext(alt_settings.pg_dsn) as conn:
        await conn.execute("insert into organisations (name) values ('foobar')")
        assert await conn.fetchval('select count(*) from organisations') == 1

    assert await prepare_database(alt_settings, False) is False

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
