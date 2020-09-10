import asyncio
import os

import pytest
from buildpg import asyncpg

from demo.settings import Settings
from foxglove import glove
from foxglove.db import lenient_conn, prepare_database
from foxglove.db.helpers import DummyPgPool, SyncDb
from foxglove.testing import Client

commit_transactions = 'KEEP_DB' in os.environ


@pytest.fixture(scope='session', name='settings')
def fix_settings():
    settings = Settings(dev_mode=False, test_mode=True)
    assert not settings.dev_mode
    glove._settings = settings

    yield settings

    glove._settings = None


@pytest.fixture(scope='session', name='alt_settings')
def fix_alt_settings(settings: Settings):
    return settings.copy(update=dict(pg_dsn='postgres://postgres@localhost:5432/foxglove_demo_alt'))


@pytest.fixture(name='db_conn_global')
async def _fix_db_conn_global(settings):
    conn = await lenient_conn(settings, with_db=False, sleep=0)

    yield conn

    await conn.close()


@pytest.fixture(name='loop')
def fix_loop(settings):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


@pytest.fixture(scope='session', name='clean_db')
def fix_clean_db(settings):
    asyncio.run(prepare_database(settings, True))


@pytest.fixture(name='wipe_db')
async def fix_wipe_db(settings):
    await prepare_database(settings, True)
    yield
    await prepare_database(settings, True)


@pytest.fixture(name='db_conn')
async def fix_db_conn(settings, clean_db):

    # with pytest.warns(DeprecationWarning):
    conn = await asyncpg.connect_b(dsn=settings.pg_dsn)

    tr = conn.transaction()
    await tr.start()

    yield DummyPgPool(conn)

    if commit_transactions:
        await tr.commit()
    else:
        await tr.rollback()
    await conn.close()


@pytest.fixture(name='glove')
async def fix_glove(db_conn):
    glove.pg = db_conn

    await glove.startup()
    await glove.redis.flushdb()

    yield glove

    await glove.shutdown()


@pytest.fixture(name='sync_db')
def fix_sync_db(db_conn):
    return SyncDb(db_conn, asyncio.get_event_loop())


class ConnContext:
    def __init__(self, dsn):
        self._dsn = dsn
        self._conn = None

    async def __aenter__(self) -> asyncpg.Connection:
        self._conn = await asyncpg.connect(self._dsn)
        return self._conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._conn.close()


class SyncConnContext:
    def __init__(self, dsn, loop=None):
        self._dsn = dsn
        self._conn = None
        self._loop = loop or asyncio.get_event_loop()

    def __enter__(self) -> SyncDb:
        self._conn = self._loop.run_until_complete(asyncpg.connect(self._dsn))
        return SyncDb(self._conn, self._loop)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._loop.run_until_complete(self._conn.close())


@pytest.fixture(name='client')
def fix_client(settings: Settings, db_conn, glove):
    app = settings.create_app()
    with Client(app) as client:
        yield client
