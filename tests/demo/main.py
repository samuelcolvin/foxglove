import asyncio
import logging

from fastapi import FastAPI, Request

from foxglove import BaseSettings, exceptions, glove

logger = logging.getLogger('main')
app = FastAPI(
    title='Foxglove Testing',
    on_startup=[glove.startup],
    on_shutdown=[glove.shutdown],
    docs_url=None,
    redoc_url='/docs',
)


@app.exception_handler(exceptions.HttpMessageError)
async def foxglove_exception_handler(request: Request, exc: exceptions.HttpMessageError):
    return exceptions.HttpMessageError.handle(exc)


@app.get('/')
def index():
    return {'app': 'foxglove-demo'}


def worker(settings: BaseSettings):
    asyncio.run(aworker(settings))


async def aworker(settings: BaseSettings):
    async with glove.context():

        async with glove.pg.acquire() as conn:
            v = await conn.fetchval('select 4^4')
        logger.info('running demo worker function, ans: %0.0f', v)
        assert isinstance(settings, BaseSettings)
