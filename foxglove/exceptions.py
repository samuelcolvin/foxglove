from typing import Any, Dict, Optional

from starlette.requests import Request
from starlette.responses import RedirectResponse

try:
    from devtools import pformat
except ImportError:  # pragma: no cover
    from pprint import pformat

__all__ = (
    'HttpRedirect',
    'redirect_handler',
    'HttpUserError',
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
    def __init__(self, location: str, *, status: int = 307):
        super().__init__(f'{status} redirect to {location!r}')
        self.status = status
        self.location = location


async def redirect_handler(request: Request, exc: HttpRedirect):
    return RedirectResponse(exc.location, status_code=exc.status)


class HttpUserError(Exception):
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


class HttpOk(HttpUserError):
    status = 200


class HttpCreated(HttpUserError):
    status = 201


class HttpAccepted(HttpUserError):
    status = 202


class HttpBadRequest(HttpUserError):
    status = 400


class HttpUnauthorized(HttpUserError):
    status = 401


class HttpPaymentRequired(HttpUserError):
    status = 402


class HttpForbidden(HttpUserError):
    status = 403


class HttpNotFound(HttpUserError):
    status = 404


class HttpMethodNotAllowed(HttpUserError):
    status = 405

    def __init__(self, message, allowed_methods, *, headers=None):
        headers = headers or {}
        headers.setdefault('Allow', ','.join(allowed_methods))
        super().__init__(message, details={'allowed_methods': allowed_methods}, headers=headers)


class HttpConflict(HttpUserError):
    status = 409


class Http470(HttpUserError):
    status = 470
    custom_reason = 'Invalid user input'
