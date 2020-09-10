from typing import TYPE_CHECKING, Any, Dict, Optional

from starlette.testclient import TestClient

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
        self, url: str, *, allow_redirects: bool = False, status: Optional[int] = 200, **kwargs
    ) -> Dict[str, Any]:
        r = self.get(url, allow_redirects=allow_redirects, **kwargs)
        if status:  # pragma: no cover
            assert r.status_code == status, r.text
        return r.json()

    def post_json(
        self, url: str, json: Any = None, *, allow_redirects: bool = False, status: Optional[int] = 200
    ) -> Dict[str, Any]:
        r = self.post(url, json=json, allow_redirects=allow_redirects)
        if status:
            assert r.status_code == status, r.text
        return r.json()
