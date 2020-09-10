from typing import Optional

from starlette.requests import Request

IP_HEADER = 'X-Forwarded-For'


def get_ip(request: Request) -> Optional[str]:
    ips = request.headers.get(IP_HEADER)
    if ips:
        return ips.split(',', 1)[0].strip(' ')
    elif client := request.scope.get('client'):
        return client[0]
