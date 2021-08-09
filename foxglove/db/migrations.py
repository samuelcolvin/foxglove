import asyncio
import logging
from typing import Optional

from buildpg.asyncpg import BuildPgConnection

from .. import glove
from ..settings import BaseSettings
from .helpers import DummyPgPool
from .patches import Patch, get_sql_section, patches
from .utils import AsyncPgContext

logger = logging.getLogger('foxglove.migrations')

__all__ = ('run_migrations',)


migrations_table = """
create table if not exists migrations (
  id serial primary key,
  function_name varchar(255) not null,
  auto_ref varchar(255) not null,
  sql_section_name varchar(255),
  sql_section_content text,
  
  ts timestamptz not null default current_timestamp,
  unique (function_name, auto_ref, sql_section_name, sql_section_content)
);
"""


async def run_migrations(settings: BaseSettings) -> Optional[int]:
    """
    Migrations in foxglove are handled by patches which are run automatically if
    foxglove spots they haven't been run before, or failed
    """
    migration_patches = [p for p in patches if p.auto_ref]
    if not migration_patches:
        return 0

    logger.info('checking %d migration patches...', len(migration_patches))
    count = 0
    up_to_date = 0
    async with AsyncPgContext(settings.pg_dsn) as conn:
        async with conn.transaction() as tr:
            v = await conn.execute(migrations_table)
            logger.info('creating migrations table: %s', v)
            await conn.execute('lock table migrations')

            for patch in migration_patches:
                patch_name = patch.func.__name__
                if patch.auto_ref_sql_section:
                    sql_section_content = get_sql_section(patch.auto_ref_sql_section, settings.sql)
                else:
                    sql_section_content = None
                migration_id = await conn.fetchval(
                    """
                    insert into migrations (function_name, auto_ref, sql_section_name, sql_section_content)
                    values ($1, $2, $3, $4)
                    on conflict (function_name, auto_ref, sql_section_name, sql_section_content) do nothing
                    returning id
                    """,
                    patch_name,
                    patch.auto_ref,
                    patch.auto_ref_sql_section,
                    sql_section_content,
                )
                if migration_id is None:
                    up_to_date += 1
                    continue

                successful = await run_patch(conn, patch, patch_name)
                if not successful:
                    logger.warning('patch failed, rolling back all %d migration patches in this session', count)
                    await tr.rollback()
                count += 1

        logger.info('%d migration patches successful, %d already up to date ✓', count, up_to_date)
        return count


async def run_patch(conn: BuildPgConnection, patch: Patch, name: str) -> bool:
    logger.info('{:-^60}'.format(f'running {name}'))
    async with conn.transaction() as patch_tr:
        glove.pg = DummyPgPool(conn)
        await glove.startup()
        kwargs = dict(conn=conn, live=True, args={'__auto_migrations__': 'true'}, logger=logger)
        try:
            if asyncio.iscoroutinefunction(patch.func):
                result = await patch.func(**kwargs)
            else:
                result = patch.func(**kwargs)
            if result is not None:
                logger.info('result: %s', result)
        except BaseException:
            logger.info('{:-^60}'.format(f'{name} failed'))
            logger.exception('Error running %s migration patch', patch.func.__name__)
            await patch_tr.rollback()
            return False
        else:
            logger.info('{:-^60}'.format(f'{name} succeeded'))
            await patch_tr.commit()
            return True
