from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

__all__ = 'PgMiddleware', 'get_db'

if TYPE_CHECKING:
    from buildpg.asyncpg import BuildPgConnection
    from starlette.responses import Response

    from ..middleware import CallNext


class GetPgConn:
    __slots__ = '_glove', '_conn'

    def __init__(self, glove):
        self._glove = glove
        self._conn = None

    async def __call__(self):
        if self._conn is None:
            self._conn = await self._glove.pg.acquire()
        return self._conn

    async def release(self):
        if self._conn is not None:
            conn = self._conn
            self._conn = None
            await self._glove.pg.release(conn)


class PgMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

        from ..main import glove

        self.glove = glove

    async def dispatch(self, request: Request, call_next: 'CallNext') -> 'Response':
        request.state.get_pg_conn = GetPgConn(self.glove)
        try:
            return await call_next(request)
        finally:
            await request.state.get_pg_conn.release()


async def get_db(request: Request) -> 'BuildPgConnection':
    return await request.state.get_pg_conn()
