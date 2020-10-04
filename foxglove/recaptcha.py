import logging
from typing import Optional

from starlette.requests import Request

from . import exceptions, glove
from .settings import BaseSettings
from .utils import get_ip

logger = logging.getLogger('foxglove.recaptcha')


async def check_recaptcha(request: Request, recaptcha_token: Optional[str], *, error_headers=None) -> None:
    client_ip = get_ip(request)

    if not recaptcha_token:
        logger.warning('recaptcha token not provided, path="%s" ip=%s', request.url.path, client_ip)
        raise exceptions.HttpBadRequest('No recaptcha value', headers=error_headers)

    settings: BaseSettings = glove.settings

    post_data = {'secret': settings.recaptcha_secret, 'response': recaptcha_token, 'remoteip': client_ip}
    r = await glove.http.post(settings.recaptcha_url, data=post_data)
    r.raise_for_status()
    data = r.json()

    if data['success'] and data['hostname'] == settings.recaptcha_hostname:
        logger.info('recaptcha success')
        return

    logger.warning(
        'recaptcha failure, path="%s" expected_host=%s ip=%s response=%s',
        request.url.path,
        settings.recaptcha_hostname,
        client_ip,
        r.text,
        extra={'data': {'recaptcha_response': data, 'recaptcha_token': recaptcha_token}},
    )
    raise exceptions.HttpBadRequest('Invalid recaptcha value', headers=error_headers)


class RecaptchaDepends:
    __slots__ = ('request',)

    def __init__(self, request: Request):
        self.request = request

    async def __call__(self, recaptcha_token: Optional[str], *, error_headers=None) -> None:
        return await check_recaptcha(self.request, recaptcha_token, error_headers=error_headers)
