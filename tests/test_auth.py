import pytest
from dirty_equals import IsBytes
from pydantic import SecretBytes

from foxglove.auth import bcrypt as auth_bcrypt, check_password_breached, check_password_correct, hash_password
from foxglove.exceptions import HttpUnprocessableEntity
from foxglove.testing import TestClient as Client


async def test_password_hash(settings):
    pw_hash = await hash_password(SecretBytes(b'testing'))

    assert pw_hash.startswith('$2b$04$')


async def test_password_correct(settings, mocker):
    check_pw = mocker.spy(auth_bcrypt, 'checkpw')
    pw_hash = await hash_password(SecretBytes(b'testing'))
    assert await check_password_correct(SecretBytes(b'testing'), pw_hash) is True
    assert check_pw.call_args.args[0] == b'testing'
    assert check_pw.call_args.args[1].startswith(b'$2b$04$')
    assert check_pw.spy_return is True


async def test_password_correct_null(settings):
    pw_hash = await hash_password(SecretBytes(b'testing'))
    assert await check_password_correct(SecretBytes(b'test\x00ing'), pw_hash) is False


async def test_password_none(settings, mocker):
    check_pw = mocker.spy(auth_bcrypt, 'checkpw')
    assert await check_password_correct(SecretBytes(b'testing'), None) is False
    assert check_pw.call_args.args[0] == b'testing'
    assert check_pw.call_args.args[1].startswith(b'$2b$04$')


@pytest.mark.parametrize(
    'password,threshold,okay',
    [
        ('password', 100, False),
        ('foobar123', 2000, True),
        ('foobar123', 100, False),
        ('this-is-not-a-known-password-8dke03m4', 0, True),
    ],
)
async def test_check_password_breached(glove, password, threshold, okay):
    if okay:
        await check_password_breached(SecretBytes(password.encode()), threshold)
    else:
        with pytest.raises(HttpUnprocessableEntity, match='This password is known to hackers'):
            await check_password_breached(SecretBytes(password.encode()), threshold)


def get_redis_keys(glove, loop):
    async def _run():
        keys = await glove.redis.keys('rate-limit*')
        if not keys:
            return None
        else:
            assert len(keys) == 1
            key = keys[0]
            return key, await glove.redis.get(key)

    return loop.run_until_complete(_run())


def test_rate_limit_error(client: Client, glove, loop):
    assert get_redis_keys(glove, loop) is None
    assert client.get_json('/rate-limit-error/') == 'ok'
    assert get_redis_keys(glove, loop) == (IsBytes(regex=br'rate-limit:GET/rate-limit-error/:testclient:\d+'), b'1')
    assert client.get_json('/rate-limit-error/?foo=bar') == 'ok'
    assert get_redis_keys(glove, loop) == (IsBytes(regex=br'rate-limit:GET/rate-limit-error/:testclient:\d+'), b'2')
    assert client.get_json('/rate-limit-error/?spam=different', status=429) == {
        'message': 'rate limit of 2 requests per 1000 seconds exceeded'
    }
    assert get_redis_keys(glove, loop) == (IsBytes(regex=br'rate-limit:GET/rate-limit-error/:testclient:\d+'), b'3')
    assert client.get_json('/rate-limit-error/', status=429) == {
        'message': 'rate limit of 2 requests per 1000 seconds exceeded'
    }
    assert get_redis_keys(glove, loop) == (IsBytes(regex=br'rate-limit:GET/rate-limit-error/:testclient:\d+'), b'4')


def test_rate_limit_return(client: Client, glove, loop):
    assert get_redis_keys(glove, loop) is None
    assert client.get_json('/rate-limit-return/') == {'request_count': 1}
    assert client.get_json('/rate-limit-return/') == {'request_count': 2}
    assert get_redis_keys(glove, loop) == (IsBytes(regex=br'rate-limit:GET/rate-limit-return/:testclient:\d+'), b'2')
