import pytest

from foxglove.testing import Client


def test_index(client: Client):
    assert client.last_request is None
    assert client.get_json('/') == {'app': 'foxglove-demo'}
    assert client.last_request.status_code == 200


def test_post_index(client: Client):
    client.get_json('/')
    with pytest.raises(AssertionError):
        assert client.post_json('/')
    assert client.last_request.status_code == 405
    assert client.post_json('/', status=None)
    assert client.last_request.status_code == 405


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


def test_return_unexpected(client: Client, caplog):
    assert client.get_json('/error/', status=400) == {'message': 'raised HttpBadRequest'}
    assert len(caplog.records) == 1, caplog.text
    assert '"GET /error/", unexpected response: 400' in caplog.text


def test_request_error(client: Client, caplog):
    r = client.get('/error/', params={'error': 'RuntimeError'})
    assert r.status_code == 500, r.text
    assert len(caplog.records) == 1, caplog.text
    assert '"GET /error/?error=RuntimeError", RuntimeError(' in caplog.text
