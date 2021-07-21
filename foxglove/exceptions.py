import json
from typing import Any, Dict, Iterable, Optional, Type, TypeVar, Union

from httpx import Response as HttpxResponse
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
    'HttpUnprocessableEntity',
    'HttpTooManyRequests',
    'Http470',
    'manual_response_error',
    'UnexpectedResponse',
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


class HttpTooManyRequests(HttpMessageError):
    status = 429


class Http470(HttpMessageError):
    status = 470
    custom_reason = 'Invalid user input'


ExcType = TypeVar('ExcType', bound=HttpMessageError)
FieldType = Union[str, Iterable[str]]


def manual_response_error(
    field: 'FieldType', msg: str, exc: Type[ExcType] = HttpUnprocessableEntity, *, error_location: str = 'body'
) -> ExcType:
    """
    Build error details that reflect how fastapi/pydantic structures errors so the frontend
    (and reactstrap_toolbox/requests.js in particular) can show user errors easily.
    """
    loc = [error_location]
    if isinstance(field, str):
        loc.append(field)
    else:
        loc += list(field)
    return exc('validation error', details=[{'loc': loc, 'msg': msg}])


class UnexpectedResponse(ValueError):
    def __init__(self, r: HttpxResponse):
        self.status_code = r.status_code
        self.response = r
        super().__init__(f'{r.request.method} {r.request.url}, unexpected response: {r.status_code}')

    @classmethod
    def check(cls, r: HttpxResponse, *, allowed_responses: Iterable[int] = (200, 201)) -> None:
        if r.status_code not in allowed_responses:
            raise cls(r)

    def __repr__(self):
        try:
            self.body = self.response.json()
        except ValueError:
            self.body = b = self.response.text
        else:
            b = json.dumps(self.body, indent=2)
        return f'UnexpectedResponse("{self.args[0]}:\n{b}")'
