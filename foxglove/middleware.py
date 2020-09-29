import json
import logging
import re
import secrets
from ipaddress import ip_address, ip_network
from operator import attrgetter
from time import time
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional

from sentry_sdk import capture_event
from sentry_sdk.utils import event_from_exception, exc_info_from_error
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import get_name as get_endpoint_name

from . import glove
from .utils import get_ip

logger = logging.getLogger('foxglove.middleware')
request_logger = logging.getLogger('foxglove.bad_requests')
CallNext = Callable[[Request], Awaitable[Response]]

__all__ = (
    'ErrorMiddleware',
    'CsrfMiddleware',
    'HostRedirectMiddleware',
    'CloudflareCheckMiddleware',
    'request_log_extra',
)


class ErrorMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: Starlette,
        should_warn: Callable[[Response], bool] = None,
        get_user: Callable[[Request], Awaitable[Dict[str, Any]]] = None,
    ):
        super().__init__(app)
        self.custom_should_warn = should_warn
        self.get_user = get_user

        from .main import glove

        self.glove = glove

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
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
        event_data = await request_log_extra(request, exc, response)
        event_data['user'] = await self.user_info(request)
        view_ref = event_data['transaction']

        if exc:
            level = 'error'
            message = f'"{line_one(request)}", {exc!r}'
            fingerprint = view_ref, request.method, repr(exc)
            request_logger.exception(message, extra=event_data)
        else:
            assert response is not None
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
                logger.critical(
                    'sentry not configured correctly, not sending message: %s',
                    message,
                    extra={'event_data': event_data},
                )

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


async def request_log_extra(
    request: Request, exc: Optional[Exception] = None, response: Optional[Response] = None
) -> Dict[str, Any]:
    extra = dict(query=dict(request.query_params))

    if start_time := getattr(request.state, 'start_time', None):
        extra['duration'] = f'{(time() - start_time) * 1000:0.2f}ms'

    if endpoint := request.scope.get('endpoint'):
        extra.update(route_endpoint=get_endpoint_name(endpoint), path_params=dict(request.path_params))

    if exc:
        extra['exception_extra'] = exc_extra(exc)
    elif response:
        extra.update(
            response_status=response.status_code,
            response_headers=dict(response.headers),
            response_body=lenient_json(await get_response_body(response)),
        )

    return dict(
        extra=extra,
        user=dict(ip_address=get_ip(request)),
        transaction=re.sub(r'/\d{2,}/', '/{number}/', str(request.url.path)),
        request=dict(
            url=str(request.url),
            query_string=request.url.query,
            cookies=dict(request.cookies),
            headers=dict(request.headers),
            method=request.method,
            data=lenient_json(request.scope.get('_body')),
            inferred_content_type=request.headers.get('Content-Type'),
        ),
    )


async def get_response_body(response: Response) -> bytes:
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

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        session_id = request.session.get(session_id_key)
        benign_request = request.method in {'HEAD', 'GET', 'OPTIONS'}
        if not benign_request and session_id is None:
            return Response(no_cookie_response, media_type='application/json', status_code=403)

        response = await call_next(request)

        # set the session id for any valid GET request
        if benign_request and response.status_code == 200 and session_id is None:
            request.session[session_id_key] = secrets.token_urlsafe()
        return response


class HostRedirectMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Starlette, host: str = None):
        super().__init__(app)
        self.host = host or glove.settings.domain
        assert self.host, 'host must not be None in HostRedirectMiddleware'

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        if request.url.hostname == self.host:
            return await call_next(request)
        else:
            return RedirectResponse(request.url.replace(hostname=self.host), status_code=301)


class IPRangeCounter:
    __slots__ = 'range', 'counter'

    def __init__(self, network_range: str):
        self.range = ip_network(network_range)
        self.counter = 0

    def __repr__(self):
        return f'IPRangeCounter({self.range}, {self.counter})'


class CloudflareCheckMiddleware(BaseHTTPMiddleware):
    default_response_body = b'Request incorrectly routed, this looks like a problem with your DNS or Proxy.'

    def __init__(self, app: Starlette, response_text: str = None):
        super().__init__(app)
        self.response_body = response_text.encode() if response_text else self.default_response_body
        # got from https://www.cloudflare.com/ips/
        self.ip_ranges = [
            IPRangeCounter('173.245.48.0/20'),
            IPRangeCounter('103.21.244.0/22'),
            IPRangeCounter('103.22.200.0/22'),
            IPRangeCounter('103.31.4.0/22'),
            IPRangeCounter('141.101.64.0/18'),
            IPRangeCounter('108.162.192.0/18'),
            IPRangeCounter('190.93.240.0/20'),
            IPRangeCounter('188.114.96.0/20'),
            IPRangeCounter('197.234.240.0/22'),
            IPRangeCounter('198.41.128.0/17'),
            IPRangeCounter('162.158.0.0/15'),
            IPRangeCounter('104.16.0.0/12'),
            IPRangeCounter('172.64.0.0/13'),
            IPRangeCounter('131.0.72.0/22'),
            IPRangeCounter('2400:cb00::/32'),
            IPRangeCounter('2606:4700::/32'),
            IPRangeCounter('2803:f800::/32'),
            IPRangeCounter('2405:b500::/32'),
            IPRangeCounter('2405:8100::/32'),
            IPRangeCounter('2a06:98c0::/29'),
            IPRangeCounter('2c0f:f248::/32'),
        ]

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        client = request.scope.get('client')
        if client and self.find_network(client[0]):
            return await call_next(request)

        extra = {'extra': await request_log_extra(request)}
        logger.warning('Request not routed through cloudflare client=%s url="%s"', client, request.url, extra=extra)
        return Response(self.response_body, status_code=400)

    def find_network(self, ip: str) -> bool:
        try:
            ip = ip_address(ip.strip())
        except ValueError:
            pass
        else:
            for r in self.ip_ranges:
                if ip in r.range:
                    r.counter += 1
                    self.ip_ranges.sort(key=attrgetter('counter'), reverse=True)
                    return True
        return False
