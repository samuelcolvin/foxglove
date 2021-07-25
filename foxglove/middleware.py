import asyncio
import json
import logging
import re
import secrets
from ipaddress import ip_address, ip_network
from operator import attrgetter
from time import time
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Literal, Optional

from sentry_sdk import capture_event
from sentry_sdk.utils import event_from_exception, exc_info_from_error
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import get_name as get_endpoint_name

from . import glove
from .exceptions import UnexpectedResponse
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
    'get_session_id',
    'update_session_id',
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


def get_session_id(request: Request) -> str:
    return request.session[session_id_key]


def update_session_id(request: Request) -> str:
    request.session[session_id_key] = new_session_id = secrets.token_urlsafe()
    return new_session_id


class CsrfMiddleware(BaseHTTPMiddleware):
    """
    Ensures a GET request has been made before post requests and that session_id is set in the session.

    This prevents CSRF especially if the cookie has same_site strict
    """

    def __init__(self, app: Starlette, should_check: Callable[[Request], bool] = None):
        super().__init__(app)
        self.should_check = should_check

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        if self.should_check and not self.should_check(request):
            return await call_next(request)

        session_id = request.session.get(session_id_key)
        benign_request = request.method in {'HEAD', 'GET', 'OPTIONS'}
        if not benign_request and session_id is None:
            return Response(no_cookie_response, media_type='application/json', status_code=403)

        response = await call_next(request)

        # set the session id for any valid GET request
        if benign_request and response.status_code == 200 and session_id is None:
            update_session_id(request)
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
        self.ip_ranges: Optional[List[IPRangeCounter]] = None

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        """
        On Heroku (and any properly configured system) we can trust the last entry in X-Forwarded-For,
        hence using that before trying client

        https://stackoverflow.com/a/37061471/949890
        """
        ip = None
        x_forwarded_for = request.headers.get('x-forwarded-for')
        if x_forwarded_for:
            ip = x_forwarded_for.rsplit(',', 1)[1].strip()
        else:
            client = request.scope.get('client')
            if client:
                ip = client[0]

        if ip and await self.is_cloudflare_ip(ip):
            return await call_next(request)

        extra = {'extra': await request_log_extra(request), 'cf_ip_ranges': self.ip_ranges}
        logger.warning('Request not routed through CloudFlare ip=%s url="%s"', ip, request.url, extra=extra)
        return Response(self.response_body, status_code=400)

    async def is_cloudflare_ip(self, ip: str) -> bool:
        try:
            ip = ip_address(ip.strip())
        except ValueError:
            pass
        else:
            if self.ip_ranges is None:
                self.ip_ranges = ip_ranges = await get_cloudflare_ips()
            else:
                ip_ranges = self.ip_ranges

            for r in ip_ranges:
                if ip in r.range:
                    r.counter += 1
                    self.ip_ranges.sort(key=attrgetter('counter'), reverse=True)
                    return True
        return False


async def get_cloudflare_ips() -> List[IPRangeCounter]:
    """
    Get a list of cloudflare IPs from https://www.cloudflare.com/ips-v4 and https://www.cloudflare.com/ips-v6,
    see https://www.cloudflare.com/en-gb/ips/ for details.
    """

    async def get_ips(v: Literal[4, 6]) -> List[IPRangeCounter]:
        r = await glove.http.get(f'https://www.cloudflare.com/ips-v{v}')
        UnexpectedResponse.check(r)
        return [IPRangeCounter(ip) for ip in r.text.strip().split('\n')]

    v4_ips, v6_ips = await asyncio.gather(get_ips(4), get_ips(6))
    ips = v4_ips + v6_ips
    logger.info('downloaded %d IPs from CloudFlare to check requests against', len(ips))
    return ips
