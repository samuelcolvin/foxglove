import asyncio
import logging
import os

from .settings import BaseSettings

logger = logging.getLogger('foxglove.redis')


async def async_flush_redis(settings: BaseSettings):
    from arq import create_pool

    redis = await create_pool(settings.redis_settings)
    await redis.flushdb()
    redis.close()
    await redis.wait_closed()


def flush_redis(settings: BaseSettings):
    if not (os.getenv('CONFIRM_FLUSH_REDIS') == 'confirm' or input('Confirm redis flush? [yN] ') == 'y'):
        logger.info('cancelling')
    else:
        logger.info('resetting database...')
        asyncio.run(async_flush_redis(settings))
        logger.info('done.')
