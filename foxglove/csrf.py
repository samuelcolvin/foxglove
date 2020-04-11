from typing import List, Optional, Pattern
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from . import BaseSettings, exceptions
from .main import glove

__all__ = ('CsrfMiddleware',)
CROSS_ORIGIN_ANY = {'Access-Control-Allow-Origin': '*'}
PROTO_HEADER = 'X-Forwarded-Proto'


class PreflightMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method != 'OPTIONS' or 'Access-Control-Request-Method' not in request.headers:
            return await call_next(request)

        if (
            request.headers.get('Access-Control-Request-Method') == 'POST'
            and path_match(request, glove.settings.preflight_paths)
            and request.headers.get('Access-Control-Request-Headers').lower() == 'content-type'
        ):
            # can't check origin here as it's null since the iframe's requests are "cross-origin"
            headers = {'Access-Control-Allow-Headers': 'Content-Type', **CROSS_ORIGIN_ANY}
            return Response('ok', headers=headers)
        else:
            raise exceptions.HttpForbidden('Access-Control checks failed', headers=CROSS_ORIGIN_ANY)


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not glove.settings.dev_mode:
            csrf_error = csrf_checks(request)
            if csrf_error:
                raise exceptions.HttpForbidden('CSRF failure: ' + csrf_error, headers=CROSS_ORIGIN_ANY)

        return await call_next(request)


def csrf_checks(request: Request) -> Optional[str]:  # noqa: C901 (ignore complexity)
    """
    Origin and Referrer checks for CSRF.
    """
    s: BaseSettings = glove.settings
    if request.method == 'GET' or path_match(request, s.csrf_except_paths):
        return

    ct = request.headers.get('Content-Type', '')
    is_upload = path_match(request, s.csrf_upload_paths)
    if is_upload:
        if not ct.startswith('multipart/form-data; boundary'):
            return 'upload path, wrong Content-Type'

    host = request.headers.get('Host')
    if host is None:
        return 'Host missing'

    origin = request.headers.get('Origin')
    if origin is None and not is_upload:
        # requiring origin unless it's an upload (firefox omits Origin on file uploads),
        # are there any other cases where this breaks?
        return 'Origin missing'

    referrer = request.headers.get('Referer')
    if referrer:
        ref = urlparse(referrer)
        # remove port from the referer to match origin and host
        ref_host = ref.netloc.rsplit(':', 1)[0]
        referrer_root = f'{ref.scheme}://{ref_host}'
    else:
        referrer_root = None

    path_root = f'{request["scheme"]}://{host}'
    if is_upload and origin is None:
        # no origin, can only check the referrer
        if referrer_root != path_root:
            return 'Referer wrong'
        else:
            return

    if origin != path_root:
        return 'Origin wrong'
    if referrer_root != path_root:
        return 'Referer wrong'


def path_match(request: Request, paths: List[Pattern]) -> bool:
    return any(p.fullmatch(request['path']) for p in paths)
