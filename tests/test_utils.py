import pytest

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
