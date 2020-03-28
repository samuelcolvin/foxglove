import os

from starlette.applications import Starlette
from starlette.middleware import Middleware
from uvicorn.importer import import_from_string

from .db import PgMiddleware
from .devtools import reload_endpoint
from .main import glove
from .settings import BaseSettings

Settings = import_from_string(os.environ['foxglove_settings_path'])
settings: BaseSettings = Settings()

glove.settings = settings
middleware = []
if settings.pg_dsn:
    middleware += [Middleware(PgMiddleware)]

routes = settings.get_routes()
if settings.dev_mode:
    foxglove_root_path = os.environ.get('foxglove_root_path')

    if foxglove_root_path:
        routes += reload_endpoint(foxglove_root_path)
    else:
        raise RuntimeError('dev_mode enabled but "foxglove_root_path" not found, can\'t add the reload endpoint')


app = Starlette(
    debug=settings.dev_mode,
    middleware=middleware,
    routes=settings.get_routes(),
    on_startup=[glove.startup],
    on_shutdown=[glove.shutdown],
)
