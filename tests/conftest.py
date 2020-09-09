import pytest

from demo.settings import Settings
from foxglove import glove
from foxglove.db import lenient_conn


@pytest.fixture(scope='session', name='settings')
def fix_settings():
    settings = Settings(
        dev_mode=False,
        test_mode=True,
        pg_dsn='postgres://postgres@localhost:5432/test_foxglove',
        redis_settings='redis://localhost:6379/6',
    )
    assert not settings.dev_mode
    glove._settings = settings

    yield settings

    glove._settings = None


@pytest.fixture(name='db_conn_global')
async def _fix_db_conn_global(settings):
    conn = await lenient_conn(settings, with_db=False)

    yield conn

    await conn.close()
