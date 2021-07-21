# flake8: noqa
from .main import glove
from .settings import BaseSettings
from .version import VERSION

__version__ = VERSION
__all__ = 'BaseSettings', 'glove', 'VERSION'
