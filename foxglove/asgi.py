import os

from starlette.applications import Starlette
from starlette.middleware import Middleware
from uvicorn.importer import import_from_string

from .db import PgMiddleware
from .main import glove

Settings = import_from_string(os.environ['foxglove_settings_path'])
settings = Settings()

glove.settings = settings
middleware = []
if settings.pg_dsn:
    middleware += [Middleware(PgMiddleware)]

app = Starlette(
    middleware=middleware, routes=settings.get_routes(), on_startup=[glove.startup], on_shutdown=[glove.shutdown],
)
