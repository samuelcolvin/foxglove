from typing import Callable

from buildpg.asyncpg import BuildPgConnection
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

__all__ = 'PgMiddleware', 'get_db'


class PgMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, check: Callable[[Request], bool] = None):
        super().__init__(app)
        self.check = check

        from ..main import glove

        self.glove = glove

    async def dispatch(self, request: Request, call_next):
        if self.check and not self.check(request):
            return await call_next(request)
        else:
            async with self.glove.pg.acquire() as conn:
                request.state.conn = conn
                return await call_next(request)


def get_db(request: Request) -> BuildPgConnection:
    return request.state.conn
