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
