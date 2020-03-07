#!/usr/bin/env python3
import asyncio
import locale
import logging
import os
import sys
from enum import Enum
from importlib import import_module
from pathlib import Path
from typing import Callable, Dict, Optional

import typer
import uvloop
from pydantic.env_settings import BaseSettings as PydanticBaseSettings
from uvicorn.importer import import_from_string
from uvicorn.main import run as uvicorn_run

from .logs import setup_logging

# from .network import check_server, wait_for_services
from .settings import BaseSettings
from .version import VERSION
from .main import FoxGlove

logger = logging.getLogger('foxglove.cli')
commands: Dict[str, Optional[Callable]] = {'auto': None}


def cmd(func: Callable):
    commands[func.__name__] = func
    return func


@cmd
def web(settings: BaseSettings, **kwargs):
    logger.info('running web server at %s...', settings.port)
    # wait_for_services(settings)
    app = FoxGlove(settings, [])
    uvicorn_run(app, host='0.0.0.0', port=settings.port)


@cmd
def worker(args, settings: BaseSettings):
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    if settings.worker_func:
        logger.info('running worker...')
        worker_func: Callable[[BaseSettings], None] = import_string(settings.worker_func)
        wait_for_services(settings)
        worker_func(settings=settings)
    else:
        raise CliError("settings.worker_func not set, can't run the worker")


@cmd
def patch(args, settings: BaseSettings):
    logger.info('running patch...')
    from .patch_methods import run_patch

    wait_for_services(settings)
    args.patches_path and import_module(args.patches_path)
    if args.extra:
        patch_name = args.extra[0]
        extra_args = args.extra[1:]
    else:
        patch_name = None
        extra_args = ()
    return run_patch(settings, patch_name, args.live, extra_args)


@cmd
def reset_database(settings: BaseSettings, **kwargs):
    from .db import reset_database

    logger.info('running reset_database...')
    reset_database(settings)


@cmd
def flush_redis(settings: BaseSettings, **kwargs):
    from .redis import flush_redis

    logger.info('running flush_redis...')
    flush_redis(settings)


@cmd
def check_web(args, settings: BaseSettings):
    url = exp_status = None
    if args.extra:
        url = args.extra[0]
        if len(args.extra) == 2:
            exp_status = int(args.extra[1])

    url = url or os.getenv('ATOOLBOX_CHECK_URL') or f'http://localhost:{settings.port}/'
    exp_status = exp_status or int(os.getenv('ATOOLBOX_CHECK_STATUS') or 200)
    logger.info('checking server is running at "%s" expecting %d...', url, exp_status)
    return check_server(url, exp_status)


@cmd
def shell(args, settings: BaseSettings):
    """
    Run an interactive python shell
    """
    from IPython import start_ipython
    from IPython.terminal.ipapp import load_default_config

    c = load_default_config()

    settings_path, settings_name = args.settings_path.rsplit('.', 1)
    exec_lines = [
        'import asyncio, base64, math, hashlib, json, os, pickle, re, secrets, sys, time',
        'from datetime import datetime, date, timedelta, timezone',
        'from pathlib import Path',
        'from pprint import pprint as pp',
        '',
        f'root_dir = "{args.root}"',
        'sys.path.append(root_dir)',
        'os.chdir(root_dir)',
        '',
        f'from {settings_path} import {settings_name}',
        'settings = Settings()',
    ]
    exec_lines += ['print("\\n    Python {v.major}.{v.minor}.{v.micro}\\n".format(v=sys.version_info))'] + [
        f"print('    {l}')" for l in exec_lines
    ]

    c.TerminalIPythonApp.display_banner = False
    c.TerminalInteractiveShell.confirm_exit = False
    c.InteractiveShellApp.exec_lines = exec_lines

    start_ipython(argv=(), config=c)


class CliError(RuntimeError):
    pass


def get_auto_command():
    command_env = os.getenv('ATOOLBOX_COMMAND')
    port_env = os.getenv('PORT')
    dyno_env = os.getenv('DYNO')
    if command_env:
        logger.info('using environment variable ATOOLBOX_COMMAND=%r to infer command', command_env)
        command_env = command_env.lower()
        if command_env != 'auto' and command_env in commands:
            return commands[command_env]
        else:
            raise CliError(f'Invalid value for ATOOLBOX_COMMAND: {command_env!r}')
    elif dyno_env:
        logger.info('using environment variable DYNO=%r to infer command', dyno_env)
        return web if dyno_env.lower().startswith('web') else worker
    elif port_env and port_env.isdigit():
        logger.info('using environment variable PORT=%s to infer command as web', port_env)
        return web
    else:
        logger.info('no environment variable found to infer command, assuming worker')
        return worker


CommandEnum = Enum('CommandEnum', [(name, name) for name in commands.keys()])


def main(
    command: CommandEnum,
    settings_path: str = typer.Option(
        os.getenv('ATOOLBOX_SETTINGS', 'settings.Settings'),
        '-s',
        '--settings',
        help=(
            'settings path (dotted, relative to the root directory), defaults to to the environment variable '
            '"ATOOLBOX_SETTINGS" or "settings.Settings"'
        ),
    ),
    live: bool = typer.Option(
        False, help='whether to run patches as live, default false, only applies to the "patch" command.',
    ),
    log: str = typer.Option(
        os.getenv('ATOOLBOX_LOG_NAME', 'app'),
        help='Root name of logs for the app, defaults to to the environment variable "ATOOLBOX_LOG_NAME" or "app"',
    ),
    root: str = typer.Option(
        os.getenv('ATOOLBOX_ROOT_DIR', '.'),
        help='root directory to run command from, defaults to to the environment variable "ATOOLBOX_ROOT_DIR" or "."',
    ),
) -> None:
    """
    foxglove command line interface
    """
    setup_logging(debug=False, main_logger_name=log)
    if command == CommandEnum.auto:
        command_function = get_auto_command()
    else:
        command_function = commands[command.value]
    command_kwargs = {
        'live': live,
    }
    try:
        sys.path.append(os.getcwd())
        root = Path(root).resolve()
        sys.path.append(str(root))
        os.chdir(str(root))

        if ':' not in settings_path:
            settings_path += ':Settings'

        try:
            settings_cls = import_from_string(settings_path)
        except (ModuleNotFoundError, ImportError) as exc:
            raise CliError(f'unable to import "{settings_path}", {exc.__class__.__name__}: {exc}')

        if not isinstance(settings_cls, type) or not issubclass(settings_cls, PydanticBaseSettings):
            raise CliError(f'settings "{settings_cls}" (from "{settings_path}"), is not a valid Settings class')

        settings = settings_cls()
        locale.setlocale(locale.LC_ALL, getattr(settings, 'locale', 'en_US.utf8'))

        return command_function(settings, **command_kwargs) or 0
    except CliError as exc:
        logger.error('%s', exc)
        return 1


def cli():
    typer.run(main)


if __name__ == '__main__':  # pragma: no cover
    cli()
