import logging

from foxglove.test_server import DummyServer
from foxglove.testing import Client


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
        'recaptcha failure, path=/captcha-check/ request_host=testserver ip=testclient '
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
        'recaptcha failure, path=/captcha-check/ request_host=testserver ip=testclient '
        'response={"success": false, "hostname": "testserver"}'
    )
