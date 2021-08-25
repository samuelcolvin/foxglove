import asyncio
import logging
import os

from buildpg.asyncpg import BuildPgPool, DuplicateDatabaseError, UniqueViolationError, create_pool_b

from ..settings import BaseSettings
from .utils import AsyncPgContext, lenient_conn

logger = logging.getLogger('foxglove.db')
__all__ = 'create_pg_pool', 'prepare_database', 'reset_database'


async def create_pg_pool(settings: BaseSettings, *, run_migrations: bool = True) -> BuildPgPool:
    await prepare_database(settings, False, run_migrations=run_migrations)
    return await create_pool_b(
        settings.pg_dsn,
        min_size=settings.pg_pool_min_size,
        max_size=settings.pg_pool_max_size,
        server_settings=settings.pg_server_settings,
    )


async def prepare_database(settings: BaseSettings, overwrite_existing: bool, *, run_migrations: bool = True) -> bool:
    db_created = await create_database(settings, overwrite_existing)
    if settings.pg_migrations and run_migrations:
        from .migrations import run_migrations as run_migrations_
        from .patches import import_patches

        patches = import_patches(settings)

        await run_migrations_(settings, patches, True, fake=db_created)
    return db_created


async def create_database(settings: BaseSettings, overwrite_existing: bool) -> bool:  # noqa: C901 (ignore complexity)
    """
    (Re)create a fresh database and run migrations.
    :param settings: settings to use for db connection
    :param overwrite_existing: whether or not to drop an existing database if it exists
    :return: whether or not a database has been (re)created
    """
    if settings.pg_db_exists:
        conn = await lenient_conn(settings, with_db=True)
        try:
            tables = await conn.fetchval("select count(*) from information_schema.tables where table_schema='public'")
            logger.info('existing tables: %d', tables)
            if tables > 0:
                if overwrite_existing:
                    logger.debug('database already exists...')
                else:
                    logger.debug('database already exists ✓')
                    return False
        finally:
            await conn.close()
    else:
        conn = await lenient_conn(settings, with_db=False)
        try:
            if not overwrite_existing:
                # don't drop connections and try creating a db if it already exists and we're not overwriting
                exists = await conn.fetchval('select 1 from pg_database where datname=$1', settings.pg_name)
                if exists:
                    logger.info('database already exists ✓')
                    return False

            await conn.execute(
                """
                select pg_terminate_backend(pg_stat_activity.pid)
                from pg_stat_activity
                where pg_stat_activity.datname = $1 AND pid <> pg_backend_pid();
                """,
                settings.pg_name,
            )
            logger.debug('attempting to create database "%s"...', settings.pg_name)
            try:
                await conn.execute(f'create database {settings.pg_name}')
            except (DuplicateDatabaseError, UniqueViolationError):
                if overwrite_existing:
                    logger.debug('database already exists...')
                else:
                    logger.debug('database already exists, skipping creation')
                    return False
            else:
                logger.debug('database did not exist, now created')

            logger.debug('settings db timezone to utc...')
            await conn.execute(f"alter database {settings.pg_name} set timezone to 'UTC';")
        finally:
            await conn.close()

    logger.debug('dropping and re-creating teh schema...')
    async with AsyncPgContext(settings.pg_dsn) as conn:
        async with conn.transaction():
            await conn.execute('drop schema public cascade;\ncreate schema public;')

    logger.debug('creating tables from model definition...')
    async with AsyncPgContext(settings.pg_dsn) as conn:
        async with conn.transaction():
            await conn.execute(settings.sql)
    logger.info('database successfully setup ✓')
    return True


def reset_database(settings: BaseSettings):
    if not (os.getenv('CONFIRM_DATABASE_RESET') == 'confirm' or input('Confirm database reset? [yN] ') == 'y'):
        logger.info('cancelling')
    else:
        logger.info('resetting database...')
        asyncio.run(prepare_database(settings, True))
        logger.info('done.')
