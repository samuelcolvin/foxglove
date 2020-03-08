from buildpg.asyncpg import BuildPgConnection
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse
from starlette.routing import Route

from foxglove import BaseSettings, glove


class FoxGloveState:
    conn: BuildPgConnection


class Request(StarletteRequest):
    state: FoxGloveState


async def homepage(request: Request):
    v = await request.state.conn.fetchval('select 4^4')
    r = await glove.http.get('https://www.example.com')
    return JSONResponse({'hello': v, 'response_status': r.status_code})


routes = [Route('/', homepage)]


class Settings(BaseSettings):
    pass
