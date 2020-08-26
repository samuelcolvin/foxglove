from typing import Any, Dict, Optional

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

try:
    from devtools import pformat
except ImportError:  # pragma: no cover
    from pprint import pformat

__all__ = (
    'HttpRedirect',
    'redirect_handler',
    'HttpMessageError',
    'HttpOk',
    'HttpCreated',
    'HttpAccepted',
    'HttpBadRequest',
    'HttpUnauthorized',
    'HttpPaymentRequired',
    'HttpForbidden',
    'HttpNotFound',
    'HttpMethodNotAllowed',
    'HttpConflict',
    'Http470',
)


class HttpRedirect(Exception):
    def __init__(self, location: str, *, status: int = 302):
        super().__init__(f'{status} redirect to {location!r}')
        self.status = status
        self.location = location


async def redirect_handler(request: Request, exc: HttpRedirect):
    return RedirectResponse(exc.location, status_code=exc.status)


class HttpMessageError(Exception):
    status: int
    custom_reason: str

    def __init__(self, message: str, *, details: Any = None, headers: Optional[Dict[str, str]] = None):
        super().__init__(message)
        self.message = message
        self.details = details
        self.headers = headers

    def __repr__(self) -> str:
        s = f'{self.__class__.__name__}({self.status}): {self.message}'
        if self.details:
            s += f'\ndetails:\n{pformat(self.details)}'
        return s

    def __str__(self) -> str:
        return repr(self)

    @staticmethod
    def handle(exc: 'HttpMessageError'):
        content = {}
        if exc.message:
            content['message'] = exc.message
        if exc.details:
            content['details'] = exc.details
        return JSONResponse(status_code=exc.status, content=content, headers=exc.headers)


class HttpOk(HttpMessageError):
    status = 200


class HttpCreated(HttpMessageError):
    status = 201


class HttpAccepted(HttpMessageError):
    status = 202


class HttpBadRequest(HttpMessageError):
    status = 400


class HttpUnauthorized(HttpMessageError):
    status = 401


class HttpPaymentRequired(HttpMessageError):
    status = 402


class HttpForbidden(HttpMessageError):
    status = 403


class HttpNotFound(HttpMessageError):
    status = 404


class HttpMethodNotAllowed(HttpMessageError):
    status = 405

    def __init__(self, message, allowed_methods, *, headers=None):
        headers = headers or {}
        headers.setdefault('Allow', ','.join(allowed_methods))
        super().__init__(message, details={'allowed_methods': allowed_methods}, headers=headers)


class HttpConflict(HttpMessageError):
    status = 409


class HttpUnprocessableEntity(HttpMessageError):
    status = 422


class Http470(HttpMessageError):
    status = 470
    custom_reason = 'Invalid user input'
