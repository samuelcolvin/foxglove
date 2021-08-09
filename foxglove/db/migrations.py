import asyncio
import logging
from typing import List, Optional

from buildpg.asyncpg import BuildPgConnection

from .. import glove
from ..settings import BaseSettings
from .helpers import DummyPgPool
from .patches import Patch, get_sql_section
from .utils import AsyncPgContext

logger = logging.getLogger('foxglove.db.migrations')

__all__ = ('run_migrations',)


migrations_table = """
create table if not exists migrations (
  id serial primary key,
  patch_name varchar(255) not null,
  auto_ref varchar(255) not null,
  sql_section_name varchar(255) not null,
  sql_section_content text not null,

  ts timestamptz not null default current_timestamp,
  unique (patch_name, auto_ref, sql_section_name, sql_section_content)
);
"""


async def run_migrations(settings: BaseSettings, patches: List[Patch]) -> Optional[int]:
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
        tr = conn.transaction()
        await tr.start()

        await conn.execute(migrations_table)
        await conn.execute('lock table migrations')

        for patch in migration_patches:
            patch_name = patch.func.__name__
            if patch.auto_ref_sql_section:
                sql_section_content = get_sql_section(patch.auto_ref_sql_section, settings.sql)
            else:
                sql_section_content = None

            # "or '-'" is required to make sure the unique constraint works since null would mean rows won't conflict
            migration_id = await conn.fetchval(
                """
                insert into migrations (patch_name, auto_ref, sql_section_name, sql_section_content)
                values ($1, $2, $3, $4)
                on conflict (patch_name, auto_ref, sql_section_name, sql_section_content) do nothing
                returning id
                """,
                patch_name,
                patch.auto_ref,
                patch.auto_ref_sql_section or '-',
                sql_section_content or '-',
            )
            if migration_id is None:
                up_to_date += 1
                continue

            successful = await run_patch(conn, patch, patch_name)
            if not successful:
                logger.warning('patch failed, rolling back all %d migration patches in this session', count)
                await tr.rollback()
                return 0

            count += 1

        await tr.commit()
        logger.info('%d migration patches run, %d already up to date ✓', count, up_to_date)
        return count


async def run_patch(conn: BuildPgConnection, patch: Patch, name: str) -> bool:
    patch_tr = conn.transaction()
    await patch_tr.start()

    default_pg = getattr(glove, 'pg', None)
    glove.pg = DummyPgPool(conn)
    # await glove.startup()
    kwargs = dict(conn=conn, live=True, args={'__auto_migrations__': 'true'}, logger=logger)
    logger.info('{:-^50}'.format(f' running {name} '))
    try:
        if asyncio.iscoroutinefunction(patch.func):
            result = await patch.func(**kwargs)
        else:
            result = patch.func(**kwargs)
        if result is not None:
            logger.info('result: %s', result)
    except BaseException:
        logger.info('{:-^50}'.format(f' {name} failed '))
        logger.exception('Error running %s migration patch', patch.func.__name__)
        await patch_tr.rollback()
        return False
    else:
        logger.info('{:-^50}'.format(f' {name} succeeded '))
        await patch_tr.commit()
        return True
    finally:
        glove.pg = default_pg
