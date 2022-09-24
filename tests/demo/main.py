import asyncio
import logging
from typing import Optional

from buildpg.asyncpg import BuildPgConnection
from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware

from foxglove import BaseSettings, exceptions, glove
from foxglove.auth import rate_limit
from foxglove.db import PgMiddleware
from foxglove.db.middleware import get_db
from foxglove.middleware import CsrfMiddleware, ErrorMiddleware
from foxglove.recaptcha import RecaptchaDepends
from foxglove.route_class import SafeAPIRoute
from foxglove.templates import FoxgloveTemplates

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


def should_check_csrf(request):
    return request.url.path != '/no-csrf/'


add_middleware(CsrfMiddleware, should_check=should_check_csrf)
add_middleware(PgMiddleware)


app = FastAPI(
    title='Foxglove Testing',
    on_startup=[glove.startup],
    on_shutdown=[glove.shutdown],
    middleware=middleware,
    docs_url=None,
    redoc_url='/docs',
)
app.router.route_class = SafeAPIRoute
app.mount('/static', StaticFiles(directory=glove.settings.static), name='static')


@app.exception_handler(exceptions.HttpMessageError)
async def foxglove_exception_handler(request: Request, exc: exceptions.HttpMessageError):
    return exceptions.HttpMessageError.handle(exc)


@app.get('/')
async def index(request: Request):
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


class CheckRecaptchaModal(BaseModel):
    recaptcha_token: Optional[str]


@app.post('/captcha-check/')
async def captcha_check(m: CheckRecaptchaModal, check_recaptcha: RecaptchaDepends = Depends(RecaptchaDepends)):
    await check_recaptcha(m.recaptcha_token)
    return {'status': 'ok'}


@app.post('/no-csrf/')
async def no_csrf():
    pass


@app.get('/rate-limit-error/', dependencies=[Depends(rate_limit(request_limit=2, interval=1000))])
async def rate_limit_raise():
    return 'ok'


@app.get('/rate-limit-return/')
async def rate_limit_return(request_count: int = Depends(rate_limit(request_limit=None, interval=1000))):
    return {'request_count': request_count}


templates = FoxgloveTemplates()


@app.get('/template/')
@templates.render('foobar.jinja')
async def render_template(request: Request):
    return {'name': 'Samuel'}


@app.get('/template/456/')
@templates.render('foobar.jinja')
def render_template_456(request: Request):
    return 456, None


@app.get('/template/spam/')
@templates.render('spam.jinja')
def render_template_spam(request: Request):
    pass
