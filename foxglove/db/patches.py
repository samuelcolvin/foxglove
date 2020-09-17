import asyncio
import logging
import re
from dataclasses import dataclass
from enum import Enum
from importlib import import_module
from typing import Callable, Dict, Type

from .. import glove
from .helpers import DummyPgPool

logger = logging.getLogger('foxglove.patch')
patches = []
__all__ = 'run_patch', 'patch', 'update_enums', 'run_sql_section'


@dataclass
class Patch:
    func: Callable
    direct: bool = False


def run_patch(patch_name: str, live: bool, args: Dict[str, str]):
    for path in getattr(glove.settings, 'patch_paths', []):
        import_module(path)

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
        logger.info(f'running patch {patch_name} direct')
    else:
        logger.info(f'running patch {patch_name} live {live}')
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_run_patch(patch, live, args)) or 0


async def _run_patch(patch: Patch, live: bool, args: Dict[str, str]):
    from .main import lenient_conn

    conn = await lenient_conn(glove.settings)
    tr = None
    if not patch.direct:
        tr = conn.transaction()
        await tr.start()
    logger.info('=' * 40)
    glove.pg = DummyPgPool(conn)
    await glove.startup()
    kwargs = dict(conn=conn, live=live, args=args, logger=logger)
    try:
        if asyncio.iscoroutinefunction(patch.func):
            result = await patch.func(**kwargs)
        else:
            result = patch.func(**kwargs)
        if result is not None:
            logger.info('result: %s', result)
    except BaseException:
        logger.info('=' * 40)
        logger.exception('Error running %s patch', patch.func.__name__)
        if not patch.direct:
            await tr.rollback()
        return 1
    else:
        logger.info('=' * 40)
        if patch.direct:
            logger.info('committed patch')
        else:
            if live:
                logger.info('live, committed patch')
                await tr.commit()
            else:
                logger.info('not live, rolling back')
                await tr.rollback()
    finally:
        await glove.shutdown()
        await conn.close()


def patch(func_=None, /, direct=False):
    if func_:
        patches.append(Patch(func=func_))
        return func_
    else:

        def wrapper(func):
            patches.append(Patch(func=func, direct=direct))
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
            await conn.execute(f"ALTER TYPE {name} ADD VALUE IF NOT EXISTS '{t.value}'")


async def run_sql_section(section_name, sql, conn):
    """
    Run a section of a sql string (eg. settings.sql) based on tags in the following format:
        -- { <chunk name>
        <sql to run>
        -- } <chunk name>
    """
    m = re.search(f'^-- *{{+ *{section_name}(.*)^-- *}}+ *{section_name}', sql, flags=re.DOTALL | re.MULTILINE)
    if not m:
        raise RuntimeError(f'chunk with name "{section_name}" not found')
    logger.info('run_sql_section running section "%s"', section_name)
    sql = m.group(1).strip(' \n')
    await conn.execute(sql)
