import logging

from foxglove import BaseSettings
from foxglove.db.patches import run_patch
from tests.conftest import SyncConnContext


def test_patch_live(settings: BaseSettings, wipe_db, caplog):
    caplog.set_level(logging.INFO)
    run_patch('insert_org', True, {})
    with SyncConnContext(settings.pg_dsn) as conn:
        assert conn.fetchval('select count(*) from organisations') == 1
    assert len(caplog.records) == 4, caplog.text
    assert 'live, committed patch' in caplog.text


def test_patch_dry_run(settings: BaseSettings, wipe_db, caplog):
    caplog.set_level(logging.INFO)
    run_patch('insert_org', False, {})
    with SyncConnContext(settings.pg_dsn) as conn:
        assert conn.fetchval('select count(*) from organisations') == 0

    assert len(caplog.records) == 4, caplog.text
    assert 'not live, rolling back' in caplog.text


def test_patch_error(settings: BaseSettings, wipe_db, caplog):
    caplog.set_level(logging.INFO)
    run_patch('insert_org', False, {'fail': '1'})
    with SyncConnContext(settings.pg_dsn) as conn:
        assert conn.fetchval('select count(*) from organisations') == 0

    assert len(caplog.records) == 4, caplog.text
    assert 'Error running insert_org patch' in caplog.text
