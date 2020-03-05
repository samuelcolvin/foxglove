from typing import List, Type, Union

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import Route

from .db import PgMiddleware
from .glove import glove
from .settings import BaseSettings


class FoxGlove(Starlette):
    def __init__(
        self,
        settings: Union[BaseSettings, Type[BaseSettings]],
        routes: List[Route],
        middleware: List[Middleware] = None,
        **kwargs,
    ):
        if not isinstance(settings, BaseSettings):
            settings = settings()
        glove.settings = settings
        if middleware is None:
            middleware = []
            if settings.pg_dsn:
                middleware += [Middleware(PgMiddleware)]
        super().__init__(
            middleware=middleware,
            routes=routes or [],
            on_startup=[glove.startup],
            on_shutdown=[glove.shutdown],
            **kwargs,
        )
