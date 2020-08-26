#!/usr/bin/env python3
import asyncio
import locale
import logging
import os
import sys
from importlib import import_module
from pathlib import Path
from typing import Callable, List

import typer
from uvicorn.importer import import_from_string
from uvicorn.main import run as uvicorn_run

from foxglove.logs import build_logging_config, setup_logging

from .main import glove
from .settings import BaseSettings
from .version import VERSION

logger = logging.getLogger('foxglove.cli')

cli = typer.Typer()
ROOT_PATH: Path
settings: BaseSettings


@cli.command()
def web():
    """
    Run the web server using uvicorn.
    """
    logger.info('running web server at %s...', settings.port)
    # wait_for_services(settings)
    uvicorn_run(
        settings.asgi_path,
        host='0.0.0.0',
        port=settings.port,
        workers=settings.web_workers,
        proxy_headers=True,
        forwarded_allow_ips='*',
        log_config=build_logging_config(),
        access_log=False,
    )


@cli.command()
def dev():
    """
    Run the web server using uvicorn for development
    """
    logger.info('running web server at %s in dev mode...', settings.port)
    os.environ.update(
        foxglove_dev_mode='TRUE', foxglove_root_path=str(ROOT_PATH),
    )
    uvicorn_run(
        settings.asgi_path,
        debug=True,
        host='127.0.0.1',
        port=settings.port,
        reload=True,
        reload_dirs=[ROOT_PATH],
        log_config=build_logging_config(),
    )


@cli.command()
def worker():
    """
    Run the worker command from settings.worker_func.
    """
    try:
        import uvloop
    except ImportError:
        pass
    else:
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    if settings.worker_func:
        logger.info('running worker...')
        worker_func: Callable[[BaseSettings], None] = import_from_string(settings.worker_func)
        # wait_for_services(settings)
        worker_func(settings=settings)
    else:
        raise CliError("settings.worker_func not set, can't run the worker")


@cli.command()
def auto():
    """
    Run either the web server or worker depending on the environment variables: FOXGLOVE_COMMAND, DYNO and PORT.
    """
    function = _get_auto_command()
    function()


def _get_auto_command() -> Callable[[], None]:
    if command_env := os.getenv('FOXGLOVE_COMMAND'):
        logger.info('using environment variable FOXGLOVE_COMMAND=%r to infer command', command_env)
        command_env = command_env.lower()
        if command_env == 'web':
            return web
        elif command_env == 'worker':
            return worker
        elif command_env != 'auto':
            raise CliError(f'Invalid value for FOXGLOVE_COMMAND: {command_env!r}')

    if dyno_env := os.getenv('DYNO'):
        logger.info('using environment variable DYNO=%r to infer command', dyno_env)
        return web if dyno_env.lower().startswith('web') else worker
    elif (port_env := os.getenv('PORT')) and port_env.isdigit():
        logger.info('using environment variable PORT=%s to infer command as web', port_env)
        return web
    else:
        logger.info('no environment variable found to infer command, assuming worker')
        return worker


@cli.command()
def patch(
    patch_name: str = typer.Argument(None),
    live: bool = False,
    patch_arg: List[str] = typer.Option(
        None,
        '--patch-args',
        '-a',
        help='extra arguments to pass to the patch, repeat for multiple arguments, usage: "-a <name>:<value>"',
    ),
):
    """
    Run a patch function to update or modify the database.
    """
    logger.info('running patch...')
    from .db.patches import run_patch

    # wait_for_services(settings)
    for path in settings.patch_paths:
        import_module(path)

    arg_lookup = {k.replace('-', '_'): v for k, v in (a.split(':', 1) for a in patch_arg)}
    return run_patch(settings, patch_name, live, arg_lookup)


@cli.command()
def reset_database():
    """
    Delete the main database and recreate it empty. THIS CAN BE DESTRUCTIVE!
    """
    from .db import reset_database

    logger.info('running reset_database...')
    reset_database(settings)


@cli.command()
def flush_redis():
    """
    Empty the redis cache.
    """
    from .redis import flush_redis

    logger.info('running flush_redis...')
    flush_redis(settings)


@cli.command()
def shell():
    """
    Run an interactive python shell.
    """
    from IPython import start_ipython
    from IPython.terminal.ipapp import load_default_config

    c = load_default_config()
    settings_path, settings_name = os.environ['foxglove_settings_path'].split(':')
    exec_lines = [
        'import asyncio, base64, math, hashlib, json, os, pickle, re, secrets, sys, time',
        'from datetime import datetime, date, timedelta, timezone',
        'from pathlib import Path',
        'from pprint import pprint as pp',
        '',
        'sys.path.append(os.getcwd())',
        f'ROOT_PATH = Path("{ROOT_PATH}")',
        'sys.path.append(str(ROOT_PATH))',
        'os.chdir(str(ROOT_PATH))',
        '',
        f'from {settings_path} import {settings_name}',
        'settings = Settings()',
    ]
    exec_lines += ['print("\\n    Python {v.major}.{v.minor}.{v.micro}\\n".format(v=sys.version_info))'] + [
        f"print('    {line}')" for line in exec_lines
    ]

    c.TerminalIPythonApp.display_banner = False
    c.TerminalInteractiveShell.confirm_exit = False
    c.InteractiveShellApp.exec_lines = exec_lines

    start_ipython(argv=(), config=c)


@cli.callback(help=f'foxglove command line interface v{VERSION}')
def callback(
    settings_path: str = typer.Option(
        os.getenv('FOXGLOVE_SETTINGS'),
        '--settings-path',
        '-s',
        help=(
            'settings path (dotted, relative to the root directory), defaults to to the environment variable '
            '"FOXGLOVE_SETTINGS" or inferred'
        ),
    ),
    root: str = typer.Option(
        os.getenv('FOXGLOVE_ROOT_DIR', '.'),
        '--root',
        '-r',
        help='root directory to run command from, defaults to to the environment variable "FOXGLOVE_ROOT_DIR" or "src"',
    ),
) -> None:
    # ugly work around, is there another way? https://github.com/tiangolo/typer/issues/55
    if {'--help', '--version'} & set(sys.argv):
        return
    global ROOT_PATH, settings

    sys.path.append(os.getcwd())
    ROOT_PATH = Path(root).resolve()
    sys.path.append(str(ROOT_PATH))
    os.chdir(str(ROOT_PATH))

    if settings_path is None:
        if (ROOT_PATH / 'settings.py').is_file():
            settings_path = 'settings'
        elif (ROOT_PATH / 'src').is_dir():
            settings_path = 'src.settings'
        else:
            raise CliError('unable to infer settings path')

    if ':' not in settings_path:
        settings_path += ':Settings'

    os.environ['foxglove_settings_path'] = settings_path
    try:
        settings = glove.settings
    except RuntimeError as exc:
        raise CliError(str(exc)) from exc
    setup_logging()

    settings_locale = getattr(settings, 'locale', None)
    if settings_locale:
        locale.setlocale(locale.LC_ALL, settings_locale)


class CliError(typer.Exit):
    def __init__(self, msg=None, code: int = 1):
        print(msg, file=sys.stdout)
        super().__init__(code)


if __name__ == '__main__':  # pragma: no cover
    cli()
