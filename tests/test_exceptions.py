import pytest
from httpx import Request as HttpxRequest, Response as HttpxResponse

from foxglove.exceptions import UnexpectedResponse


def test_unexpected_response_ok(settings):
    UnexpectedResponse.check(HttpxResponse(200, request=HttpxRequest('GET', url='https://example.com')))


def test_unexpected_response_error(settings):
    r = HttpxResponse(403, request=HttpxRequest('GET', url='https://example.com'), text='{"foo": 1}')
    with pytest.raises(UnexpectedResponse) as exc_info:
        UnexpectedResponse.check(r)

    assert repr(exc_info.value) == (
        'UnexpectedResponse("GET https://example.com, unexpected response: 403:\n{\n  "foo": 1\n}")'
    )
