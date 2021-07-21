import asyncio

import pytest

from pydantic import SecretBytes

from foxglove.auth import hash_password, check_password_correct, bcrypt as auth_bcrypt, check_password_breached
from foxglove.exceptions import HttpUnprocessableEntity

pytestmark = pytest.mark.asyncio


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

