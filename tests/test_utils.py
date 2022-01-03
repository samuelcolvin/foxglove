import pytest

from foxglove.testing import Client
from foxglove.utils import dict_not_none, list_not_none


def test_list_not_none():
    assert list_not_none(1, 2, 3) == [1, 2, 3]
    assert list_not_none(1, 2, None, 3) == [1, 2, 3]
    assert list_not_none(1, 2, False, 3) == [1, 2, False, 3]


def test_dict_not_none():
    assert dict_not_none({'a': 1, 'b': None, 'c': 3}) == {'a': 1, 'c': 3}
    assert dict_not_none(a=1, c=3) == {'a': 1, 'c': 3}
    with pytest.raises(TypeError, match='dict_not_none expected at most 1 argument, got 2'):
        dict_not_none({'a': 1}, {'b': None})
    with pytest.raises(TypeError, match='dict_not_none must be a dict, got list'):
        dict_not_none([1])


def test_null_json_error(client: Client):
    client.get_json('/')
    assert client.post_json('/create-user/', {'first_name': 'Samuel\x00', 'last_name': 'Colvin'}, status=400) == {
        'detail': 'There was an error parsing the body'
    }
