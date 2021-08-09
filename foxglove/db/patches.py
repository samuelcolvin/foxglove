import asyncio
import logging
import re
from dataclasses import dataclass
from enum import Enum
from importlib import import_module
from typing import Any, Callable, Dict, List, Type, Union

from .. import glove
from ..settings import BaseSettings
from .helpers import DummyPgPool

logger = logging.getLogger('foxglove.db.patch')
_patch_list: List['Patch'] = []
__all__ = (
    'run_patch',
    'patch',
    'update_enums',
    'run_sql_section',
    'Patch',
    'get_sql_section',
    'import_patches',
)


@dataclass
class Patch:
    func: Callable[..., Any]
    direct: bool = False
    auto_run: Union[None, bool, str] = None
    auto_sql_section: str = None


def run_patch(patch_name: str, live: bool, args: Dict[str, str]):
    patches = import_patches(glove.settings)

    if patch_name is None:
        logger.info(
            'available patches:\n{}'.format(
                '\n'.join('  {}: {}'.format(p.func.__name__, (p.func.__doc__ or '').strip('\n ')) for p in patches)
            )
        )
        return 0

    patch_lookup = {p.func.__name__: p for p in patches}
    try:
        patch = patch_lookup[patch_name]
    except KeyError:
        logger.error('patch "%s" not found in patches: %s', patch_name, [p.func.__name__ for p in patches])
        return 1

    if patch.direct:
        if not live:
            logger.error('direct patches must be called with "--live"')
            return 1
        log_msg = f'running patch {patch_name} direct'
    else:
        log_msg = f'running patch {patch_name} {"live" if live else "not live"}'
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_run_patch(patch, live, args, log_msg)) or 0


async def _run_patch(patch: Patch, live: bool, args: Dict[str, str], log_msg: str):
    from .main import lenient_conn

    conn = await lenient_conn(glove.settings)
    tr = None
    if not patch.direct:
        tr = conn.transaction()
        await tr.start()
    glove.pg = DummyPgPool(conn)
    await glove.startup(run_migrations=False)
    kwargs = dict(conn=conn, live=live, args=args, logger=logger)
    logger.info('{:-^50}'.format(f' {log_msg} '))
    try:
        if asyncio.iscoroutinefunction(patch.func):
            result = await patch.func(**kwargs)
        else:
            result = patch.func(**kwargs)
        if result is not None:
            logger.info('result: %s', result)
    except BaseException:
        logger.info('{:-^50}'.format(' error '))
        logger.exception('Error running %s patch', patch.func.__name__)
        if not patch.direct:
            await tr.rollback()
        return 1
    else:
        if patch.direct:
            logger.info('{:-^50}'.format(' committed patch '))
        else:
            if live:
                logger.info('{:-^50}'.format(' live, committed patch '))
                await tr.commit()
            else:
                logger.info('{:-^50}'.format(' not live, rolling back '))
                await tr.rollback()
    finally:
        await glove.shutdown()
        await conn.close()


def patch(func_=None, /, direct=False, auto_run: Union[str, bool] = None, auto_sql_section: str = None):
    if func_:
        _patch_list.append(Patch(func_))
        return func_
    else:

        def wrapper(func):
            if direct and auto_run:
                raise TypeError(
                    'patches with direct=True, cannot also have auto_run set since migrations '
                    'run in a single transaction'
                )
            _patch_list.append(Patch(func, direct, auto_run, auto_sql_section))
            return func

        return wrapper


@patch
async def rerun_sql(*, conn, **kwargs):
    """
    rerun the contents of settings.sql_path.
    """
    # this require you to use "CREATE X IF NOT EXISTS" everywhere
    await conn.execute(glove.settings.sql)


async def update_enums(enums: Dict[str, Type[Enum]], conn):
    """
    update sql enums from python enums, this requires @patch(direct=True) on the patch
    """
    for name, enum in enums.items():
        for t in enum:
            await conn.execute(f"alter type {name} add value if not exists '{t.value}'")


def get_sql_section(section_name: str, sql: str) -> str:
    """
    retrieve a block of code from a sql string (eg. settings.sql) based on tags in the following format:
        -- { <chunk name>
        <sql to run>
        -- } <chunk name>
    """
    m = re.search(f'^-- *{{+ *{section_name}(.*)^-- *}}+ *{section_name}', sql, flags=re.DOTALL | re.MULTILINE)
    if not m:
        raise RuntimeError(f'chunk with name "{section_name}" not found')
    return m.group(1).strip(' \n')


async def run_sql_section(section_name, sql, conn):
    """
    Run a section of a sql string (eg. settings.sql) based on tags in the following format:
        -- { <chunk name>
        <sql to run>
        -- } <chunk name>
    """
    sql = get_sql_section(section_name, sql)
    logger.info('run_sql_section running section "%s"', section_name)
    await conn.execute(sql)


def import_patches(settings: BaseSettings) -> List[Patch]:
    for path in getattr(settings, 'patch_paths', []):
        import_module(path)
    return _patch_list
