from typing import Dict, List, Optional, TypeVar

from starlette.requests import Request

__all__ = 'get_ip', 'list_not_none', 'dict_not_none'

IP_HEADER = 'X-Forwarded-For'


def get_ip(request: Request) -> Optional[str]:
    ips = request.headers.get(IP_HEADER)
    if ips:
        return ips.split(',', 1)[0].strip(' ')
    elif client := request.scope.get('client'):
        return client[0]


T = TypeVar('T')


def list_not_none(*items: T) -> List[T]:
    return [item for item in items if item is not None]


def dict_not_none(*args: Dict[str, T], **kwargs: T) -> Dict[str, T]:
    d = {}
    if args:
        if len(args) > 1:
            raise TypeError(f'dict_not_none expected at most 1 argument, got {len(args)}')
        d = args[0]
        if not isinstance(d, dict):
            raise TypeError(f'dict_not_none must be a dict, got {d.__class__.__name__}')
    if kwargs:
        d.update(kwargs)
    return {key: value for key, value in d.items() if value is not None}
