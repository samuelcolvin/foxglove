from typing import Callable

from fastapi import Request, Response
from fastapi.routing import APIRoute

__all__ = ('KeepBodyAPIRoute',)


class KeepBodyRequest(Request):
    async def body(self) -> bytes:
        if not hasattr(self, '_body'):
            chunks = []
            async for chunk in self.stream():
                chunks.append(chunk)
            self.scope['_body'] = self._body = b''.join(chunks)
        return self._body


class KeepBodyAPIRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            request = KeepBodyRequest(request.scope, request.receive)
            return await original_route_handler(request)

        return custom_route_handler
