from typing import Callable

from fastapi import Request, Response
from fastapi.routing import APIRoute

try:
    import ujson
except ImportError:  # pragma: no branch
    import json as ujson

__all__ = ('SafeAPIRoute',)


class SafeRequest(Request):
    async def body(self) -> bytes:
        """
        Read the body like normal but store it in the request scope for use in error handling middleware.
        """
        if not hasattr(self, '_body'):
            chunks = []
            async for chunk in self.stream():
                chunks.append(chunk)
            self.scope['_body'] = self._body = b''.join(chunks)
        return self._body

    async def json(self) -> str:
        """
        Like the super json method, but will raise an error if null bytes are found in the JSON, also use
        ujson to parse the JSON when available.

        The error here is caught by foxglove.routing.get_request_handler
        """
        if not hasattr(self, '_json'):
            body = await self.body()
            if b'\\u0000' in body:
                raise ValueError('Invalid JSON body containing null bytes')
            self._json = ujson.loads(body)
        return self._json


class SafeAPIRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            request = SafeRequest(request.scope, request.receive)
            return await original_route_handler(request)

        return custom_route_handler
