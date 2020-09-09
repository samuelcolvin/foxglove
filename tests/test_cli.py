from typer.testing import CliRunner

from foxglove import BaseSettings
from foxglove.cli import cli
from tests.conftest import SyncConnContext

runner = CliRunner()


def test_print_commands():
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0, result.output
    assert 'foxglove command line interface' in result.output
    assert 'Run the web server using uvicorn for development' in result.output


def test_patches_print():
    result = runner.invoke(cli, ['-s', 'demo.settings', 'patch'])
    assert result.exit_code == 0, result.output
    assert 'rerun_sql: rerun the contents of settings.sql_path' in result.output
    assert 'check_args: check args are working right' in result.output


def test_patches_check_args():
    result = runner.invoke(cli, ['-s', 'demo.settings', 'patch', 'check_args', '-a', 'user_id:123', '-a', 'co:Testing'])
    assert result.exit_code == 0, result.output
    assert "checking args: {'user_id': '123', 'co': 'Testing'}" in result.output


def test_patches_insert_org_live(settings: BaseSettings):
    result = runner.invoke(cli, ['-s', 'demo.settings', 'patch', 'insert_org', '--live'])
    assert result.exit_code == 0, result.output
    with SyncConnContext(settings.pg_dsn) as conn:
        assert conn.fetchval('select count(*) from organisations') == 1


# def test_patches_insert_org_dry(settings: BaseSettings):
#     result = runner.invoke(cli, ['-s', 'demo.settings', 'patch', 'insert_org'])
#     assert result.exit_code == 0, result.output
#     with SyncConnContext(settings.pg_dsn) as conn:
#         assert conn.fetchval('select count(*) from organisations') == 0
