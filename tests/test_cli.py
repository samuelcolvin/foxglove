import pytest
from typer.testing import CliRunner

from foxglove import glove
from foxglove.cli import cli

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


def test_web_no_settings(mocker):
    mock_uvicorn_run = mocker.patch('foxglove.cli.uvicorn_run')
    result = runner.invoke(cli, ['web'])
    assert result.exit_code == 1, result.output
    assert 'unable to infer settings path' in result.output
    assert mock_uvicorn_run.call_count == 0


def test_web(mocker):
    mock_uvicorn_run = mocker.patch('foxglove.cli.uvicorn_run')
    result = runner.invoke(cli, ['-s', 'demo.settings', 'web'])
    assert result.exit_code == 0, result.output
    assert 'running web server at 8000...' in result.output
    mock_uvicorn_run.assert_called_once()
    assert mock_uvicorn_run.call_args.kwargs['host'] == '0.0.0.0'
    assert mock_uvicorn_run.call_args.kwargs['port'] == 8000
    assert mock_uvicorn_run.call_args.kwargs.get('reload') is None
    assert mock_uvicorn_run.call_args.kwargs.get('debug') is None
    assert mock_uvicorn_run.call_args.kwargs.get('access_log') is False


def test_dev(mocker):
    mock_uvicorn_run = mocker.patch('foxglove.cli.uvicorn_run')
    result = runner.invoke(cli, ['-s', 'demo.settings:Settings', 'dev'])
    assert result.exit_code == 0, result.output
    assert 'running web server at 8000 in dev mode...' in result.output
    mock_uvicorn_run.assert_called_once()
    assert mock_uvicorn_run.call_args.kwargs['host'] == '127.0.0.1'
    assert mock_uvicorn_run.call_args.kwargs['port'] == 8000
    assert mock_uvicorn_run.call_args.kwargs.get('reload') is True
    assert mock_uvicorn_run.call_args.kwargs.get('debug') is True
    assert mock_uvicorn_run.call_args.kwargs.get('access_log') is None


def test_auto_web(mocker):
    mock_uvicorn_run = mocker.patch('foxglove.cli.uvicorn_run')
    result = runner.invoke(cli, ['-s', 'demo.settings', 'auto'], env={'FOXGLOVE_COMMAND': 'web'})
    assert result.exit_code == 0, result.output
    assert 'running web server at 8000...' in result.output
    assert mock_uvicorn_run.call_count == 1
    assert mock_uvicorn_run.call_args.kwargs['port'] == 8000

    del glove._settings
    result = runner.invoke(cli, ['-s', 'demo.settings', 'auto'], env={'DYNO': 'WEB.1'})
    assert result.exit_code == 0, result.output
    assert 'running web server at 8000...' in result.output
    assert mock_uvicorn_run.call_count == 2
    assert mock_uvicorn_run.call_args.kwargs['port'] == 8000

    del glove._settings
    result = runner.invoke(cli, ['-s', 'demo.settings', 'auto'], env={'PORT': '5000'})
    assert result.exit_code == 0, result.output
    assert 'running web server at 5000...' in result.output
    assert mock_uvicorn_run.call_count == 3
    assert mock_uvicorn_run.call_args.kwargs['port'] == 5000


@pytest.mark.filterwarnings('ignore::DeprecationWarning')
def test_worker():
    result = runner.invoke(cli, ['-s', 'demo.settings', 'worker'])
    assert result.exit_code == 0, result.output
    assert 'running worker...' in result.output
    assert 'running demo worker function, ans: 256' in result.output
