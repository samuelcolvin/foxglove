import asyncio
import logging
import os

from async_timeout import timeout
from buildpg import asyncpg
from buildpg.asyncpg import BuildPgConnection

from ..settings import BaseSettings

logger = logging.getLogger('foxglove.db')
__all__ = 'create_pg_pool', 'prepare_database', 'reset_database', 'lenient_conn'


async def create_pg_pool(settings: BaseSettings) -> asyncpg.BuildPgPool:
    await prepare_database(settings, False)
    return await asyncpg.create_pool_b(
        settings.pg_dsn,
        min_size=settings.pg_pool_min_size,
        max_size=settings.pg_pool_max_size,
    )


async def prepare_database(settings: BaseSettings, overwrite_existing: bool) -> bool:  # noqa: C901 (ignore complexity)
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
            except (asyncpg.DuplicateDatabaseError, asyncpg.UniqueViolationError):
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
    conn = await asyncpg.connect(dsn=settings.pg_dsn)
    try:
        async with conn.transaction():
            await conn.execute('drop schema public cascade;\ncreate schema public;')
    finally:
        await conn.close()

    logger.debug('creating tables from model definition...')
    conn = await asyncpg.connect(dsn=settings.pg_dsn)
    try:
        async with conn.transaction():
            await conn.execute(settings.sql)
    finally:
        await conn.close()
    logger.info('database successfully setup ✓')
    return True


def reset_database(settings: BaseSettings):
    if not (os.getenv('CONFIRM_DATABASE_RESET') == 'confirm' or input('Confirm database reset? [yN] ') == 'y'):
        logger.info('cancelling')
    else:
        logger.info('resetting database...')
        asyncio.run(prepare_database(settings, True))
        logger.info('done.')


async def lenient_conn(settings: BaseSettings, *, with_db: bool = True, sleep: float = 1) -> BuildPgConnection:
    if with_db:
        dsn = settings.pg_dsn
    else:
        dsn, _ = settings.pg_dsn.rsplit('/', 1)

    for retry in range(8, -1, -1):
        try:
            async with timeout(2):
                conn = await asyncpg.connect_b(dsn=dsn)
        except (asyncpg.PostgresError, OSError) as e:
            if retry == 0:
                raise
            else:
                logger.warning('pg temporary connection error "%s", %d retries remaining...', e, retry)
                await asyncio.sleep(sleep)
        else:
            log = logger.debug if retry == 8 else logger.info
            log('pg connection successful, version: %s', await conn.fetchval('SELECT version()'))
            return conn
