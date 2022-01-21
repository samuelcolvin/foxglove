import logging

import pytest

from foxglove import exceptions
from foxglove.recaptcha import check_recaptcha
from foxglove.test_server import DummyServer
from foxglove.testing import TestClient as Client


def test_success(client: Client, settings, dummy_server: DummyServer, caplog):
    caplog.set_level(logging.INFO)
    settings.recaptcha_url = f'{dummy_server.server_name}/recaptcha_url/'
    assert client.get_json('/') == {'app': 'foxglove-demo'}
    assert client.post_json('/captcha-check/', {'recaptcha_token': '__ok__'}) == {'status': 'ok'}
    assert dummy_server.log == ['POST /recaptcha_url/ > 200 (recaptcha __ok__)']
    logs = [r.message for r in caplog.records if r.name == 'foxglove.recaptcha']
    assert logs == ['recaptcha success']


def test_no_token(client: Client, settings, dummy_server: DummyServer):
    settings.recaptcha_url = f'{dummy_server.server_name}/recaptcha_url/'
    assert client.get_json('/') == {'app': 'foxglove-demo'}
    assert client.post_json('/captcha-check/', {}, status=400) == {'message': 'No recaptcha value'}
    assert dummy_server.log == []


def test_wrong_host(client: Client, settings, dummy_server: DummyServer, caplog):
    caplog.set_level(logging.INFO)
    settings.recaptcha_url = f'{dummy_server.server_name}/recaptcha_url/'
    assert client.get_json('/') == {'app': 'foxglove-demo'}
    assert client.post_json('/captcha-check/', {'recaptcha_token': '__wrong_host__'}, status=400) == {
        'message': 'Invalid recaptcha value'
    }
    assert dummy_server.log == ['POST /recaptcha_url/ > 200 (recaptcha __wrong_host__)']
    logs = [r.message for r in caplog.records if r.name == 'foxglove.recaptcha']
    assert len(logs) == 1
    assert logs[0] == (
        'recaptcha failure, path=/captcha-check/ allowed_hosts=testserver ip=testclient '
        'response={"success": true, "hostname": "__wrong_host__"}'
    )


def test_bad_token(client: Client, settings, dummy_server: DummyServer, caplog):
    caplog.set_level(logging.INFO)
    settings.recaptcha_url = f'{dummy_server.server_name}/recaptcha_url/'
    assert client.get_json('/') == {'app': 'foxglove-demo'}
    assert client.post_json('/captcha-check/', {'recaptcha_token': 'bad'}, status=400) == {
        'message': 'Invalid recaptcha value'
    }
    assert dummy_server.log == ['POST /recaptcha_url/ > 200 (recaptcha bad)']
    logs = [r.message for r in caplog.records if r.name == 'foxglove.recaptcha']
    assert len(logs) == 1
    assert logs[0] == (
        'recaptcha failure, path=/captcha-check/ allowed_hosts=testserver ip=testclient '
        'response={"success": false, "hostname": "testserver"}'
    )


def test_settings_origin(client: Client, settings, dummy_server: DummyServer, caplog):
    caplog.set_level(logging.INFO)
    settings.recaptcha_url = f'{dummy_server.server_name}/recaptcha_url/'
    settings.origin = 'https://example.com'
    try:
        assert client.get_json('/') == {'app': 'foxglove-demo'}
        assert client.post_json('/captcha-check/', {'recaptcha_token': '__ok__ host:example.com'}) == {'status': 'ok'}
        assert dummy_server.log == ['POST /recaptcha_url/ > 200 (recaptcha __ok__ host:example.com)']
        logs = [r.message for r in caplog.records if r.name == 'foxglove.recaptcha']
        assert logs == ['recaptcha success']
    finally:
        settings.origin = None


async def test_direct_ok(create_request, settings, dummy_server: DummyServer, glove):
    settings.recaptcha_url = f'{dummy_server.server_name}/recaptcha_url/'
    await check_recaptcha(create_request(), '__ok__')


async def test_direct_request_origin(create_request, settings, dummy_server: DummyServer, glove):
    settings.recaptcha_url = f'{dummy_server.server_name}/recaptcha_url/'
    await check_recaptcha(create_request(headers={'origin': 'https://foo.com'}), '__ok__ host:foo.com')


async def test_direct_wrong_host(create_request, settings, dummy_server: DummyServer, glove):
    settings.recaptcha_url = f'{dummy_server.server_name}/recaptcha_url/'
    with pytest.raises(exceptions.HttpBadRequest):
        await check_recaptcha(create_request(), '__ok__ host:foobar.com')


async def test_allowed_hosts(create_request, settings, dummy_server: DummyServer, glove):
    settings.recaptcha_url = f'{dummy_server.server_name}/recaptcha_url/'
    await check_recaptcha(create_request(), '__ok__ host:foobar.com', allowed_hosts={'foobar.com'})
