from typer.testing import CliRunner

from foxglove.cli import cli
runner = CliRunner()


def test_print_commands():
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert 'foxglove command line interface' in result.output
    assert 'Run the web server using uvicorn for development' in result.output
