from typing import TYPE_CHECKING, Any, Dict, Optional

from starlette.testclient import TestClient

try:
    from devtools.prettier import pformat
except ImportError:
    from pprint import pformat

try:
    import pytest
except ImportError:
    pytest = None

if TYPE_CHECKING:
    from requests import Response


class Client(TestClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_request: Optional['Response'] = None

    def request(self, *args, **kwargs) -> 'Response':
        r = super().request(*args, **kwargs)
        self.last_request = r
        return r

    def get_json(
        self,
        url: str,
        *,
        allow_redirects: bool = False,
        status: Optional[int] = 200,
        headers: Dict[str, str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        r = self.get(url, allow_redirects=allow_redirects, headers=headers, **kwargs)
        check_response(r, status)
        return r.json()

    def post_json(
        self,
        url: str,
        json: Any = None,
        *,
        allow_redirects: bool = False,
        status: Optional[int] = 200,
        headers: Dict[str, str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        r = self.post(url, json=json, allow_redirects=allow_redirects, headers=headers, **kwargs)
        check_response(r, status)
        return r.json()


def check_response(response: 'Response', expected_status: Optional[int]) -> None:
    if expected_status is None or response.status_code == expected_status:
        return

    try:
        body = pformat(response.json())
    except ValueError:
        body = response.text

    req = response.request
    msg = (
        f'{req.method} {req.url} returned unexpected status: {response.status_code} (expected {expected_status}), '
        f'body:\n{body}'
    )

    if pytest:  # pragma: no branch
        pytest.fail(msg)
    else:  # pragma: no cover
        raise ValueError(msg)
