import logging

from foxglove import BaseSettings
from foxglove.db.patches import run_patch
from tests.conftest import SyncConnContext


def test_patch_live(settings: BaseSettings, wipe_db, caplog):
    caplog.set_level(logging.INFO)
    run_patch('insert_org', True, {})
    with SyncConnContext(settings.pg_dsn) as conn:
        assert conn.fetchval('select count(*) from organisations') == 1

    assert [m for m in caplog.messages if m != 'sentry not initialised'] == [
        '--------- running patch insert_org live ----------',
        '------------- live, committed patch --------------',
    ]


def test_patch_dry_run(settings: BaseSettings, wipe_db, caplog):
    caplog.set_level(logging.INFO)
    run_patch('insert_org', False, {})
    with SyncConnContext(settings.pg_dsn) as conn:
        assert conn.fetchval('select count(*) from organisations') == 0

    assert [m for m in caplog.messages if m != 'sentry not initialised'] == [
        '------- running patch insert_org not live --------',
        '------------- not live, rolling back -------------',
    ]


def test_patch_error(settings: BaseSettings, wipe_db, caplog):
    caplog.set_level(logging.INFO)
    run_patch('insert_org', False, {'fail': '1'})
    with SyncConnContext(settings.pg_dsn) as conn:
        assert conn.fetchval('select count(*) from organisations') == 0

    assert [m for m in caplog.messages if m != 'sentry not initialised'] == [
        '------- running patch insert_org not live --------',
        '--------------------- error ----------------------',
        'Error running insert_org patch',
    ]
