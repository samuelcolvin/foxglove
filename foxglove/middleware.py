import json
import logging
import re
import secrets
from time import time
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional

from sentry_sdk import capture_event
from sentry_sdk.utils import event_from_exception, exc_info_from_error
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import get_name as get_endpoint_name

from . import glove
from .utils import get_ip

logger = logging.getLogger('foxglove.middleware')
request_logger = logging.getLogger('foxglove.bad_requests')

__all__ = 'ErrorMiddleware', 'CsrfMiddleware'


class ErrorMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        should_warn: Callable[[Response], bool] = None,
        get_user: Callable[[Request], Awaitable[Dict[str, Any]]] = None,
    ):
        super().__init__(app)
        self.custom_should_warn = should_warn
        self.get_user = get_user

        from .main import glove

        self.glove = glove

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        try:
            request.state.start_time = get_request_start(request)

            try:
                response = await call_next(request)
            except Exception as exc:
                await self.log(request, exc=exc)
                return Response('Internal Server Error', media_type='text/plain', status_code=500)
            else:
                if self.should_warn(response):
                    await self.log(request, response=response)
                return response
        except Exception:  # pragma: no cover
            # not sure if this is required, but better to keep it
            logger.critical('unhandled error in ErrorMiddleware', exc_info=True)
            raise

    async def log(
        self, request: Request, *, exc: Optional[Exception] = None, response: Optional[Response] = None
    ) -> None:
        extra = dict(duration=f'{(time() - request.state.start_time) * 1000:0.2f}ms', query=dict(request.query_params))
        if endpoint := request.scope.get('endpoint'):
            extra.update(route_endpoint=get_endpoint_name(endpoint), path_params=dict(request.path_params))

        if exc:
            extra['exception_extra'] = exc_extra(exc)
        else:
            assert response is not None

            extra.update(
                response_status=response.status_code,
                response_headers=dict(response.headers),
                response_body=lenient_json(await self.response_body(response)),
            )

        view_ref = re.sub(r'\d{2,}', '{number}', str(request.url.path))
        event_data = dict(
            extra=extra,
            user=await self.user_info(request),
            transaction=view_ref,
            request=dict(
                url=str(request.url),
                query_string=request.url.query,
                cookies=dict(request.cookies),
                headers=dict(request.headers),
                method=request.method,
                data=lenient_json(getattr(request, '_body', None)),
                inferred_content_type=request.headers.get('Content-Type'),
            ),
        )

        if exc:
            level = 'error'
            message = f'"{line_one(request)}", {exc!r}'
            fingerprint = view_ref, request.method, repr(exc)
            request_logger.exception(message, extra=event_data)
        else:
            level = 'warning'
            message = f'"{line_one(request)}", unexpected response: {response.status_code}'
            request_logger.warning(message, extra=event_data)
            fingerprint = view_ref, request.method, str(response.status_code)

        if glove.settings.sentry_dsn:
            hint = None
            if exc:
                exc_data, hint = event_from_exception(exc_info_from_error(exc))
                event_data.update(exc_data)

            event_data.update(message=message, level=level, logger='foxglove.request_errors', fingerprint=fingerprint)
            if not capture_event(event_data, hint):
                logger.error('sentry not configured, not sending message: %s', message, extra=event_data)

    def should_warn(self, response: Response) -> bool:
        if self.custom_should_warn:
            return self.custom_should_warn(response)
        else:
            return response.status_code > 310

    async def user_info(self, request: Request) -> Dict[str, Any]:
        user = dict(ip_address=get_ip(request))
        if get_user := self.get_user:
            try:
                user.update(await get_user(request))
            except Exception:
                logger.exception('error getting user for middleware logging')
        return user

    @staticmethod
    async def response_body(response: Response) -> bytes:
        if hasattr(response, 'body'):
            return response.body
        else:
            body_chunks = []
            async for chunk in response.body_iterator:
                if not isinstance(chunk, bytes):
                    chunk = chunk.encode(response.charset)
                body_chunks.append(chunk)

            response.body_iterator = async_gen_list(body_chunks)
            return b''.join(body_chunks)


async def async_gen_list(list_: List[bytes]) -> AsyncGenerator[bytes, None]:
    for c in list_:
        yield c


def line_one(request: Request) -> str:
    line = f'{request.method} {request.url.path}'
    if q := request.url.query:
        line += f'?{q}'
    return line


def get_request_start(request):
    try:
        return float(request.headers.get('X-Request-Start', '.')) / 1000
    except ValueError:
        return time()


def exc_extra(exc: Exception):
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


session_id_key = 'session_id'
no_cookie_response = """\
{
  "message": "Permission Denied, no session set, updates not permitted"
}
"""


class CsrfMiddleware(BaseHTTPMiddleware):
    """
    Ensures a GET request has been made before post requests and that session_id is set in the session.

    This prevents CSRF especially if the cookie has same_site strict
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        session_id = request.session.get(session_id_key)
        benign_request = request.method in {'HEAD', 'GET', 'OPTIONS'}
        if not benign_request and session_id is None:
            return Response(no_cookie_response, media_type='application/json', status_code=403)

        response = await call_next(request)

        # set the session id for any valid GET request
        if benign_request and response.status_code == 200 and session_id is None:
            request.session[session_id_key] = secrets.token_urlsafe()
        return response
