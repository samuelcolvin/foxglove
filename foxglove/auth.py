import asyncio
import hashlib
import secrets
from functools import lru_cache
from time import time
from typing import Optional

import bcrypt
from fastapi import Request
from pydantic import SecretBytes

from . import glove
from .exceptions import HttpTooManyRequests, UnexpectedResponse, manual_response_error

__all__ = 'rate_limit', 'check_password_breached', 'check_password_correct', 'hash_password'


def rate_limit(*, request_limit: Optional[int], interval: int):
    async def check_rate_limit(request: Request) -> int:
        cache_key = f'rate-limit:{request.method}{request.url.path}:{time() // interval:0.0f}'
        with await glove.redis as conn:
            pipe = conn.pipeline()
            pipe.unwatch()
            pipe.incr(cache_key)
            pipe.expire(cache_key, interval)
            _, request_count, _ = await pipe.execute()
            if request_limit is None:
                return request_count or 0
            elif request_count > request_limit:
                raise HttpTooManyRequests(f'rate limit of {request_limit} requests per {interval} seconds exceeded')

    return check_rate_limit


async def check_password_breached(
    pw: SecretBytes,
    threshold: int,
    *,
    field_name: str = 'password',
    error_message: str = 'This password is known to hackers! Please use a different password',
) -> None:
    """
    Check a password against https://haveibeenpwned.com/API/v2#SearchingPwnedPasswordsByRange
    to see if it's known to hackers
    """
    pw_hash = hashlib.sha1(pw.get_secret_value()).hexdigest()
    r = await glove.http.get(f'https://api.pwnedpasswords.com/range/{pw_hash[:5]}')
    UnexpectedResponse.check(r)

    hash_suffix = pw_hash[5:].upper()
    for line in filter(None, r.text.split('\r\n')):
        line_suffix, count_str = line.split(':', 1)
        if line_suffix == hash_suffix:
            if int(count_str) > threshold:
                raise manual_response_error(field_name, error_message)
            break


def _hash_password(password: SecretBytes) -> str:
    return bcrypt.hashpw(password.get_secret_value(), bcrypt.gensalt(glove.settings.bcrypt_rounds)).decode()


async def hash_password(password: SecretBytes) -> str:
    """
    Hash a password to save in the db, run in a thread executor, I've checked that bcrypt releases the GIL
    """
    return await asyncio.get_running_loop().run_in_executor(None, _hash_password, password)


@lru_cache
def _get_dummy_hash() -> bytes:
    """
    This is only used to run checkpw when no password is available to prevent timing attack, however to guard
    against accidental usage, we hash a random byte string.
    """
    return bcrypt.hashpw(secrets.token_urlsafe().encode(), bcrypt.gensalt(glove.settings.bcrypt_rounds))


def _check_password(password: SecretBytes, expected_hash: Optional[str]) -> bool:
    """
    I've checked and bcrypt releases the GIL
    """
    if expected_hash is None:
        # this should never actually be used to check if a password is correct, just to avoid timing attack
        # by running checkpw on all login attempts
        bcrypt.checkpw(password.get_secret_value(), _get_dummy_hash())
        # we return False anyway to be sure
        return False
    else:

        return bcrypt.checkpw(password.get_secret_value(), expected_hash.encode())


async def check_password_correct(password: SecretBytes, expected_hash: Optional[str]) -> bool:
    """
    Check if a password is valid, run in a thread executor, I've checked that bcrypt releases the GIL
    """
    return await asyncio.get_running_loop().run_in_executor(None, _check_password, password, expected_hash)
