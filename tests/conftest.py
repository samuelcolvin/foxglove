import asyncio
import os

import pytest
from buildpg import asyncpg
from starlette.requests import Request
from starlette.responses import Response

from demo.settings import Settings
from foxglove import glove
from foxglove.db import lenient_conn, prepare_database
from foxglove.db.helpers import DummyPgPool, SyncDb
from foxglove.test_server import create_dummy_server
from foxglove.testing import TestClient

commit_transactions = 'KEEP_DB' in os.environ


@pytest.fixture(scope='session', name='settings')
def fix_settings():
    settings = Settings(dev_mode=False, test_mode=True, bcrypt_rounds=4)
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
def fix_loop(event_loop):
    asyncio.set_event_loop(event_loop)
    return event_loop


@pytest.fixture(scope='session', name='clean_db')
def fix_clean_db(settings):
    asyncio.run(prepare_database(settings, True, run_migrations=False))


@pytest.fixture(name='wipe_db')
async def fix_wipe_db(settings):
    await prepare_database(settings, True, run_migrations=False)
    yield
    await prepare_database(settings, True, run_migrations=False)


@pytest.fixture(name='db_conn')
async def fix_db_conn(settings, clean_db):
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
async def fix_glove(db_conn, loop):
    glove.pg = db_conn

    await glove.startup()
    await glove.redis.flushdb()

    yield glove

    await glove.shutdown()


@pytest.fixture(name='sync_db')
def fix_sync_db(db_conn, loop):
    return SyncDb(db_conn, loop)


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
def fix_client(settings: Settings, db_conn, glove, loop):
    app = settings.create_app()
    with TestClient(app, loop=loop) as client:
        yield client


@pytest.fixture(name='client_sentry')
def fix_client_sentry(settings: Settings, db_conn, glove, loop):
    settings.sentry_dsn = 'https://123@example.com/789'
    glove._settings = settings
    app = settings.create_app()
    with TestClient(app, loop=loop) as client:
        yield client
    settings.sentry_dsn = None


@pytest.fixture(name='dummy_server')
async def _fix_dummy_server(loop):
    ds = await create_dummy_server(loop)
    yield ds
    await ds.stop()


@pytest.fixture(name='create_request')
def _fix_create_request(settings: Settings):
    app = settings.create_app()

    async def endpoint(request: Request):
        return Response()

    class CreateRequest:
        def __init__(self, _app):
            self.app = _app

        def __call__(self, method='GET', path='/', headers=None, client_addr='testclient', **extra_scope):
            _headers = {'host': 'testserver', 'user-agent': 'testclient', 'connection': 'keep-alive'}
            if headers:
                _headers.update(headers)
            scope = {
                'type': 'http',
                'http_version': '1.1',
                'method': method,
                'path': path,
                'root_path': '',
                'scheme': 'http',
                'query_string': b'',
                'headers': [(k.lower().encode(), v.encode()) for k, v in _headers.items()],
                'client': [
                    client_addr,
                    50000,
                ],
                'server': [
                    'testserver',
                    80,
                ],
                'extensions': {
                    'http.response.template': {},
                },
                'app': app,
                'state': {},
                'session': {},
                'endpoint': endpoint,
                'path_params': {},
                **extra_scope,
            }
            return Request(scope, None, None)

    return CreateRequest(app)
