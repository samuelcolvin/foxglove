from foxglove.testing import TestClient as Client


def test_index(client: Client):
    assert client.last_response is None
    assert client.get_json('/') == {'app': 'foxglove-demo'}
    assert client.last_response.status_code == 200


def test_post_index(client: Client):
    client.get_json('/')
    assert client.post_json('/', status=None)
    assert client.last_response.status_code == 405


def test_request_error(client: Client, mocker):
    fail_mock = mocker.patch('foxglove.testing.pytest.fail')
    client.post_json('/')
    fail_mock.called_once()


def test_create_user(client: Client):
    client.get_json('/')
    assert client.post_json('/create-user/', {'first_name': 'Samuel', 'last_name': 'Colvin'}, status=201) == {
        'id': 123,
        'v': 16,
    }


def test_no_session_id(client: Client):
    assert client.post_json('/create-user/', {'first_name': 'Samuel', 'last_name': 'Colvin'}, status=403) == {
        'message': 'Permission Denied, no session set, updates not permitted'
    }


def test_errors_raise_unexpected(client: Client, caplog):
    assert client.get_json('/error/', status=400) == {'message': 'raised HttpBadRequest'}
    assert len(caplog.records) == 1, caplog.text
    assert '"GET /error/", unexpected response: 400' in caplog.text
    r = caplog.records[0]
    assert r.user == {'ip_address': 'testclient'}
    assert r.request['url'] == 'http://testserver/error/'
    assert r.extra['route_endpoint'] == 'error'
    assert r.extra['response_body'] == {'message': 'raised HttpBadRequest'}


def test_errors_exception(client: Client, caplog):
    r = client.get('/error/', params={'error': 'RuntimeError'})
    assert r.status_code == 500, r.text
    assert len(caplog.records) == 1, caplog.text
    assert '"GET /error/?error=RuntimeError", RuntimeError(' in caplog.text
    assert caplog.records[0].request['url'] == 'http://testserver/error/?error=RuntimeError'


def test_errors_request_return_unexpected(client: Client, caplog, mocker):
    m = mocker.patch('foxglove.middleware.capture_event')
    assert client.get_json('/error/', params={'error': 'return'}, status=400) == {'error': 'return'}
    assert len(caplog.records) == 1, caplog.text
    assert '"GET /error/?error=return", unexpected response: 400' in caplog.text
    r = caplog.records[0]
    assert r.user == {'ip_address': 'testclient'}
    assert r.request['url'] == 'http://testserver/error/?error=return'
    assert r.extra['route_endpoint'] == 'error'
    assert r.extra['response_body'] == {'error': 'return'}
    assert m.call_count == 0


def test_errors_expected_sentry(client_sentry: Client, caplog, mocker):
    m = mocker.patch('foxglove.middleware.capture_event')
    assert client_sentry.get_json('/error/', status=400) == {'message': 'raised HttpBadRequest'}
    assert len(caplog.records) == 1, caplog.text
    msg = '"GET /error/", unexpected response: 400'
    assert msg in caplog.text

    m.assert_called_once()
    assert m.call_args.args[0]['message'] == msg
    assert m.call_args.args[0]['fingerprint'] == ('/error/', 'GET', '400')
    assert m.call_args.args[1] is None


def test_errors_exception_sentry(client_sentry: Client, caplog, mocker):
    m = mocker.patch('foxglove.middleware.capture_event')
    r = client_sentry.get('/error/', params={'error': 'RuntimeError'})
    assert r.status_code == 500, r.text
    assert len(caplog.records) == 1, caplog.text
    msg = '"GET /error/?error=RuntimeError", RuntimeError(\'raised RuntimeError\')'
    assert msg in caplog.text

    m.assert_called_once()
    assert m.call_args.args[0]['message'] == msg
    assert m.call_args.args[0]['fingerprint'] == ('/error/', 'GET', "RuntimeError('raised RuntimeError')")
    assert m.call_args.args[1] is not None


def test_null_json_error(client: Client):
    client.get_json('/')
    assert client.post_json('/create-user/', {'first_name': 'Samuel\x00', 'last_name': 'Colvin'}, status=400) == {
        'detail': 'There was an error parsing the body'
    }
