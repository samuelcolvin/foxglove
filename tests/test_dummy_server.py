import asyncio
import os

import pytest

from foxglove.test_server import DummyServer, Offline

pytestmark = pytest.mark.asyncio


async def test_dummy_get(dummy_server: DummyServer, glove):
    r = await glove.http.get(f'http://localhost:{dummy_server.server.port}/status/200/')
    assert r.status_code == 200, r.text
    assert dummy_server.log == ['GET /status/200/ > 200']


async def test_grecaptcha_dummy(dummy_server: DummyServer, glove):
    r = await glove.http.post(
        f'http://localhost:{dummy_server.server.port}/grecaptcha_url/', data={'response': '__ok__'}
    )
    assert r.status_code == 200, r.text
    assert r.json() == {'success': True, 'hostname': '127.0.0.1'}
    assert dummy_server.log == ['POST /grecaptcha_url/ > 200 (grecaptcha __ok__)']


async def test_grecaptcha_dummy_400(dummy_server: DummyServer, glove):
    r = await glove.http.post(
        f'http://localhost:{dummy_server.server.port}/grecaptcha_url/', data={'response': '__400__'}
    )
    assert r.status_code == 400, r.text
    assert r.json() == {}
    assert dummy_server.log == ['POST /grecaptcha_url/ > 400 (grecaptcha __400__)']


async def test_grecaptcha_dummy_other(dummy_server: DummyServer, glove):
    r = await glove.http.post(f'http://localhost:{dummy_server.server.port}/grecaptcha_url/')
    assert r.status_code == 200, r.text
    assert r.json() == {'success': False, 'hostname': '127.0.0.1'}
    assert dummy_server.log == ['POST /grecaptcha_url/ > 200 (grecaptcha None)']


async def test_dummy_405(dummy_server: DummyServer, glove):
    r = await glove.http.get(f'http://localhost:{dummy_server.server.port}/grecaptcha_url/')
    assert r.status_code == 405, r.text
    assert dummy_server.log == ['GET /grecaptcha_url/ > 405']


def test_offline_online(loop):
    o = Offline(loop)
    assert bool(o) is False
    assert bool(o) is False


def test_offline_offline(mocker, loop, capsys):
    ci_value = os.getenv('CI')
    if ci_value:
        del os.environ['CI']
    try:
        m = mocker.patch('aiodns.DNSResolver.query', side_effect=asyncio.TimeoutError)
        o = Offline(loop)
        assert bool(o) is True
        assert bool(o) is True
        m.assert_called_once()
        captured = capsys.readouterr()
        assert captured.out == ''
        assert captured.err == '\nnot online: TimeoutError \n\n'
    finally:
        if ci_value:
            os.environ['CI'] = ci_value


_offline = Offline()
skip_if_offline = pytest.mark.skipif(_offline, reason='not online')


@skip_if_offline
def test_offline_decorator():
    print("we're online!")
