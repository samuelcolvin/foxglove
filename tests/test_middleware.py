import pytest
from starlette.requests import Request
from starlette.responses import Response

from foxglove.middleware import CloudflareCheckMiddleware, HostRedirectMiddleware
from foxglove.testing import Client

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


async def test_cloudflare_ok(create_request):
    req: Request = create_request(client_addr='162.158.186.183')
    m = CloudflareCheckMiddleware(create_request.app)

    assert repr(m.ip_ranges[0]) == 'IPRangeCounter(173.245.48.0/20, 0)'

    r = await m.dispatch(req, next_function)
    assert r.status_code == 200, r.body

    assert repr(m.ip_ranges[0]) == 'IPRangeCounter(162.158.0.0/15, 1)'


async def test_cloudflare_bad(create_request):
    req: Request = create_request()
    m = CloudflareCheckMiddleware(create_request.app)

    assert repr(m.ip_ranges[0]) == 'IPRangeCounter(173.245.48.0/20, 0)'

    r = await m.dispatch(req, next_function)
    assert r.status_code == 400, r.body
    assert r.body.startswith(b'Request incorrectly routed, this looks like')

    assert repr(m.ip_ranges[0]) == 'IPRangeCounter(173.245.48.0/20, 0)'


async def test_cloudflare_bad2(create_request):
    req: Request = create_request(client_addr='63.143.42.246')
    m = CloudflareCheckMiddleware(create_request.app, 'badness!')

    assert repr(m.ip_ranges[0]) == 'IPRangeCounter(173.245.48.0/20, 0)'

    r = await m.dispatch(req, next_function)
    assert r.status_code == 400, r.body
    assert r.body == b'badness!'

    assert repr(m.ip_ranges[0]) == 'IPRangeCounter(173.245.48.0/20, 0)'


async def test_cloudflare_multiple(create_request):
    m = CloudflareCheckMiddleware(create_request.app)
    assert repr(m.ip_ranges[0]) == 'IPRangeCounter(173.245.48.0/20, 0)'
    assert repr(m.ip_ranges[1]) == 'IPRangeCounter(103.21.244.0/22, 0)'

    for client_ip in '162.158.186.183', '104.16.0.0', '162.158.92.59':
        req: Request = create_request(client_addr=client_ip)
        r = await m.dispatch(req, next_function)
        assert r.status_code == 200, r.body

    assert repr(m.ip_ranges[0]) == 'IPRangeCounter(162.158.0.0/15, 2)'
    assert repr(m.ip_ranges[1]) == 'IPRangeCounter(104.16.0.0/12, 1)'
    assert repr(m.ip_ranges[2]) == 'IPRangeCounter(173.245.48.0/20, 0)'


def test_index(client: Client):
    assert client.post_json('/no-csrf/') is None
    assert client.last_request.status_code == 200
