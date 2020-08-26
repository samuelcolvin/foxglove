import json
import logging
from time import time
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger('foxglove.middleware')


class ErrorMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, should_warn: Callable = None):
        super().__init__(app)
        self.custom_should_warn = should_warn

        from .main import glove

        self.glove = glove

    def should_warn(self, response: Response):
        if self.custom_should_warn:
            return self.custom_should_warn(response)
        else:
            return response.status_code > 310 and response.status_code not in {401, 404, 422, 470}

    async def dispatch(self, request: Request, call_next):
        request.state.start_time = get_request_start(request)
        r = await call_next(request)
        if self.should_warn(r):
            logger.warning('"%s", unexpected response: %s', line_one(request), r.status_code)
        return r
        # try:
        #     r = await call_next(request)
        # except Exception:
        #     # todo replace this with custom error handling and remove standard sentry middleware
        #     logger.exception('"%s", %r', line_one(request), exc, extra={'exception_extra': exc_extra(exc)})
        #     return Response('Internal Server Error', status_code=500)
        # else:
        #     if self.should_warn(r):
        #         logger.warning(f'"%s", unexpected response: %s', line_one(request), r.status_code)
        #     return r


def line_one(request: Request) -> str:
    line = f'{request.method} {request.url.path}'
    if q := request.scope['query_string']:
        try:
            line += f'?{q.decode()}'
        except ValueError:
            line += f'?{q}'
    return line


def get_request_start(request):
    try:
        return float(request.headers.get('X-Request-Start', '.')) / 1000
    except ValueError:
        return time()


def exc_extra(exc):
    exception_extra = getattr(exc, 'extra', None)
    if exception_extra:
        try:
            v = exception_extra()
        except Exception:
            pass
        else:
            return lenient_json(v)


def lenient_json(v: Any) -> Any:
    if isinstance(v, (str, bytes)):
        try:
            return json.loads(v)
        except (ValueError, TypeError):
            pass
    return v
