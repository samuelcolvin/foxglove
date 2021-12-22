import pytest
from starlette.requests import Request
from starlette.responses import Response

import foxglove.middleware
from foxglove.middleware import CloudflareCheckMiddleware, HostRedirectMiddleware
from foxglove.testing import TestClient as Client

pytestmark = pytest.mark.asyncio


async def next_function(request: Request):
    return Response('ok')


async def test_host_redirect_ok(create_request):
    req: Request = create_request(headers={'host': 'good'})
    m = HostRedirectMiddleware(create_request.app, 'good')
    r = await m.dispatch(req, next_function)
    assert r.status_code == 200, r.body
    assert r.headers.get('location') is None
    assert r.body == b'ok'


async def test_host_redirect_wrong(create_request):
    req: Request = create_request(headers={'host': 'bad'})
    m = HostRedirectMiddleware(create_request.app, 'good')
    r = await m.dispatch(req, next_function)
    assert r.status_code == 301, r.body
    assert r.headers.get('location') == 'http://good/'
    assert r.body == b''


async def test_cloudflare_ok_header(create_request, glove):
    req: Request = create_request(headers={'x-forwarded-for': '09.155.161.152,1.1.1.1,162.158.90.14'})
    m = CloudflareCheckMiddleware(create_request.app)

    assert m.ip_ranges is None

    r = await m.dispatch(req, next_function)
    assert r.status_code == 200, r.body

    assert isinstance(m.ip_ranges, list)
    assert len(m.ip_ranges) == 22
    assert repr(m.ip_ranges[0]) == 'IPRangeCounter(162.158.0.0/15, 1)'


async def test_cloudflare_ok_client(create_request, glove):

    req: Request = create_request(client_addr='162.158.186.183')
    m = CloudflareCheckMiddleware(create_request.app)

    assert m.ip_ranges is None

    r = await m.dispatch(req, next_function)
    assert r.status_code == 200, r.body

    assert isinstance(m.ip_ranges, list)
    assert repr(m.ip_ranges[0]) == 'IPRangeCounter(162.158.0.0/15, 1)'


async def test_cloudflare_bad(create_request, glove):
    req: Request = create_request()
    m = CloudflareCheckMiddleware(create_request.app)

    assert m.ip_ranges is None

    r = await m.dispatch(req, next_function)
    assert r.status_code == 400, r.body
    assert r.body.startswith(b'Request incorrectly routed, this looks like')

    assert m.ip_ranges is None


async def test_cloudflare_bad2(create_request, glove):
    req: Request = create_request(client_addr='63.143.42.246')
    m = CloudflareCheckMiddleware(create_request.app, 'badness!')

    assert m.ip_ranges is None

    r = await m.dispatch(req, next_function)
    assert r.status_code == 400, r.body
    assert r.body == b'badness!'

    assert isinstance(m.ip_ranges, list)
    assert repr(m.ip_ranges[0]) == 'IPRangeCounter(173.245.48.0/20, 0)'


async def test_cloudflare_single_ip(create_request, glove):
    req: Request = create_request(headers={'x-forwarded-for': '1.1.1.1'})
    m = CloudflareCheckMiddleware(create_request.app)

    assert m.ip_ranges is None

    r = await m.dispatch(req, next_function)
    assert r.status_code == 400, r.body
    assert r.body.startswith(b'Request incorrectly routed, this looks like')

    assert isinstance(m.ip_ranges, list)
    assert len(m.ip_ranges) == 22


async def test_cloudflare_multiple(create_request, glove, mocker):
    get_cloudflare_ips_spy = mocker.spy(foxglove.middleware, 'get_cloudflare_ips')

    m = CloudflareCheckMiddleware(create_request.app)
    assert m.ip_ranges is None

    for client_ip in '162.158.186.183', '104.16.0.0', '162.158.92.59':
        req: Request = create_request(client_addr=client_ip)
        r = await m.dispatch(req, next_function)
        assert r.status_code == 200, r.body

    assert isinstance(m.ip_ranges, list)
    assert repr(m.ip_ranges[0]) == 'IPRangeCounter(162.158.0.0/15, 2)'
    assert repr(m.ip_ranges[1]) == 'IPRangeCounter(104.16.0.0/13, 1)'
    assert repr(m.ip_ranges[2]) == 'IPRangeCounter(173.245.48.0/20, 0)'
    assert get_cloudflare_ips_spy.call_count == 1


def test_index(client: Client):
    assert client.post_json('/no-csrf/') is None
    assert client.last_response.status_code == 200
