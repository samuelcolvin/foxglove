import asyncio
import logging
from typing import List

from asyncpg import LockNotAvailableError
from buildpg.asyncpg import BuildPgConnection

from .. import glove
from ..settings import BaseSettings
from .helpers import DummyPgPool
from .patches import Patch, get_sql_section
from .utils import AsyncPgContext

logger = logging.getLogger('foxglove.db.migrations')

__all__ = ('run_migrations',)


migrations_table_name = 'migrations'
migrations_table_sql = f"""
create table if not exists {migrations_table_name} (
  id serial primary key,
  ts timestamptz not null default current_timestamp,
  ref varchar(255) not null,
  sql_section text not null,
  fake boolean not null,
  unique (ref, sql_section)
);
"""


async def run_migrations(settings: BaseSettings, patches: List[Patch], live: bool, *, fake: bool = False) -> int:
    """
    Migrations in foxglove are handled by patches which are run automatically if
    foxglove spots they haven't been run before
    """
    migration_patches = [p for p in patches if p.auto_run]
    if not migration_patches:
        return 0

    count = 0
    up_to_date = 0
    async with AsyncPgContext(settings.pg_dsn) as conn:
        tr = conn.transaction()
        await tr.start()

        if not await conn.fetchval('select 1 from pg_tables where tablename=$1', migrations_table_name):
            await conn.execute(migrations_table_sql)
            logger.info('%s table created', migrations_table_name)

        try:
            await conn.execute(f'lock table {migrations_table_name} nowait')
        except LockNotAvailableError:
            logger.debug('another transaction has locked %s, skipping migrations here', migrations_table_name)
            await tr.rollback()
            return 0

        default_pg = getattr(glove, 'pg', None)
        glove.pg = DummyPgPool(conn)
        logger.info('checking %d migration patches...', len(migration_patches))
        for patch in migration_patches:
            if patch.auto_sql_section:
                content = get_sql_section(patch.auto_sql_section, settings.sql)
                sql_section = f'{patch.auto_sql_section}::\n{content}'
            else:
                # '-' is required to make the unique constraint work since null would mean rows wouldn't conflict
                sql_section = '-'

            patch_ref = patch.func.__name__
            if isinstance(patch.auto_run, str):
                patch_ref += f':{patch.auto_run}'
            migration_id = await conn.fetchval(
                f"""
                insert into {migrations_table_name} (ref, sql_section, fake)
                values ($1, $2, $3)
                on conflict (ref, sql_section) do nothing
                returning id
                """,
                patch_ref,
                sql_section,
                fake,
            )
            if migration_id is None:
                up_to_date += 1
                continue

            if fake:
                logger.info('faked migration %s', patch_ref)
            else:
                successful = await run_patch(conn, patch, patch_ref, live)
                if not successful:
                    logger.warning('patch failed, rolling back all %d migration patches in this session', count)
                    await tr.rollback()
                    glove.pg = default_pg
                    return 0

            count += 1

        glove.pg = default_pg
        verb = 'faked' if fake else 'run'
        if live:
            await tr.commit()
            if count == 0:
                logger.info('all %d migrations already up to date ✓', up_to_date)
            else:
                logger.info('%d migration patches %s, %d already up to date ✓', count, verb, up_to_date)
        else:
            await tr.rollback()
            logger.info(
                '%d migration patches %s, %d already up to date, not live rolling back', count, verb, up_to_date
            )

    return count


async def run_patch(conn: BuildPgConnection, patch: Patch, ref: str, live: bool) -> bool:
    kwargs = dict(conn=conn, live=live, args={'__migration__': 'true'}, logger=logger)
    logger.info('{:-^50}'.format(f' {ref} ... '))
    try:
        if asyncio.iscoroutinefunction(patch.func):
            result = await patch.func(**kwargs)
        else:
            result = patch.func(**kwargs)
        if result is not None:
            logger.info('result: %s', result)
    except BaseException:
        logger.info('{:-^50}'.format(f' {ref} failed '))
        logger.exception('Error running %s migration patch', patch.func.__name__)
        return False
    else:
        logger.info('{:-^50}'.format(f' {ref} ✓ '))
        return True
