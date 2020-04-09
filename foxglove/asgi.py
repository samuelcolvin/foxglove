import os

from starlette.applications import Starlette
from uvicorn.importer import import_from_string

from .devtools import reload_endpoint
from .exceptions import HttpRedirect, redirect_handler
from .main import glove
from .settings import BaseSettings

Settings = import_from_string(os.environ['foxglove_settings_path'])
settings: BaseSettings = Settings()

glove.settings = settings

routes = list(settings.get_routes())
if settings.dev_mode:
    foxglove_root_path = os.environ.get('foxglove_root_path')

    if foxglove_root_path:
        routes += reload_endpoint(foxglove_root_path)
    else:
        raise RuntimeError('dev_mode enabled but "foxglove_root_path" not found, can\'t add the reload endpoint')


exception_handlers = {HttpRedirect: redirect_handler}

app = Starlette(
    debug=settings.dev_mode,
    routes=routes,
    middleware=list(settings.get_middleware()),
    exception_handlers=exception_handlers,
    on_startup=[glove.startup],
    on_shutdown=[glove.shutdown],
)
