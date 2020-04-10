import os

from uvicorn.importer import import_from_string

from .main import glove
from .settings import BaseSettings

Settings = import_from_string(os.environ['foxglove_settings_path'])
settings: BaseSettings = Settings()

glove.settings = settings
app = settings.create_app()
