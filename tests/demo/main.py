import asyncio
import logging

from buildpg.asyncpg import BuildPgConnection
from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware

from foxglove import BaseSettings, exceptions, glove
from foxglove.db import PgMiddleware
from foxglove.db.middleware import get_db
from foxglove.middleware import CsrfMiddleware, ErrorMiddleware

logger = logging.getLogger('main')


# first middleware is outer here
middleware = []


def add_middleware(mw: type, **kwargs):
    middleware.append(Middleware(mw, **kwargs))


add_middleware(ErrorMiddleware)
add_middleware(
    SessionMiddleware,
    secret_key=glove.settings.secret_key,
    session_cookie=glove.settings.cookie_name,
    same_site='strict',
)
add_middleware(CsrfMiddleware)
add_middleware(PgMiddleware)


app = FastAPI(
    title='Foxglove Testing',
    on_startup=[glove.startup],
    on_shutdown=[glove.shutdown],
    middleware=middleware,
    docs_url=None,
    redoc_url='/docs',
)


@app.exception_handler(exceptions.HttpMessageError)
async def foxglove_exception_handler(request: Request, exc: exceptions.HttpMessageError):
    return exceptions.HttpMessageError.handle(exc)


@app.get('/')
def index():
    return {'app': 'foxglove-demo'}


class UserInfo(BaseModel):
    first_name: str
    last_name: str
    email: str = None


@app.post('/create-user/', status_code=201)
async def create_user(user: UserInfo, conn: BuildPgConnection = Depends(get_db)):
    logger.info('user: %s', user)
    v = await conn.fetchval('select 4^2')
    return {'id': 123, 'v': v}


@app.get('/error/', status_code=400)
async def error(error: str = 'raise'):
    if error == 'RuntimeError':
        raise RuntimeError('raised RuntimeError')
    elif error == 'raise':
        raise exceptions.HttpBadRequest('raised HttpBadRequest')
    else:
        return {'error': error}


def worker(settings: BaseSettings):
    asyncio.run(aworker(settings))


async def aworker(settings: BaseSettings):
    async with glove.context():

        async with glove.pg.acquire() as conn:
            v = await conn.fetchval('select 4^4')
        logger.info('running demo worker function, ans: %0.0f', v)
        assert isinstance(settings, BaseSettings)
