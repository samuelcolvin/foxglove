import logging
import logging.config
import os
import traceback
from io import StringIO
from typing import Any, Dict

from uvicorn.logging import DefaultFormatter

from .main import glove

try:
    import pygments
    from pygments.formatters import Terminal256Formatter
    from pygments.lexers import Python3TracebackLexer
except ImportError:  # pragma: no cover
    pyg_lexer = pyg_formatter = None
else:
    pyg_lexer, pyg_formatter = Python3TracebackLexer(), Terminal256Formatter(style='vim')

try:
    from devtools import pformat as format_extra
    from devtools.ansi import isatty, sformat
except ImportError:  # pragma: no cover
    from pprint import pformat

    isatty = False
    sformat = None

    def format_extra(extra, highlight):
        return pformat(extra)


logger = logging.getLogger('foxglove.logs')

# only way to get "extra" from a LogRecord is to look in record.__dict__ and ignore all the standard keys
standard_record_keys = {
    'name',
    'msg',
    'args',
    'levelname',
    'levelno',
    'pathname',
    'filename',
    'module',
    'exc_info',
    'exc_text',
    'stack_info',
    'lineno',
    'funcName',
    'created',
    'msecs',
    'relativeCreated',
    'thread',
    'threadName',
    'processName',
    'process',
    'message',
    'color_message',
}


class HighlightExtraFormatter(DefaultFormatter):
    def __init__(self, *args, **kwargs):
        self.sentry_active = bool(glove.settings.sentry_dsn)
        super().__init__(*args, **kwargs)

    def formatMessage(self, record):
        s = super().formatMessage(record)
        if not self.sentry_active:
            extra = {k: v for k, v in record.__dict__.items() if k not in standard_record_keys}
            if extra:
                s += '\nExtra: ' + format_extra(extra, highlight=self.should_use_colors())
        return s

    def formatException(self, ei):
        if self.sentry_active:
            return super().formatException(ei)
        sio = StringIO()
        traceback.print_exception(*ei, file=sio)
        stack = sio.getvalue()
        sio.close()
        if self.should_use_colors() and pyg_lexer:
            return pygments.highlight(stack, lexer=pyg_lexer, formatter=pyg_formatter).rstrip('\n')
        else:
            return stack


class NotWarnings(logging.Filter):
    def filter(self, record):
        return record.levelno < logging.WARNING


def get_env_multiple(*names):
    for name in names:
        v = os.getenv(name, None) or os.getenv(name.lower(), None)
        if v:
            return v


def setup_sentry() -> bool:
    if glove.settings.sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration, ignore_logger

        sentry_sdk.init(
            dsn=glove.settings.sentry_dsn,
            integrations=[LoggingIntegration(level=logging.INFO, event_level=logging.WARNING)],
            release=glove.settings.release,
            environment=glove.settings.environment,
            server_name=get_env_multiple('DYNO', 'SERVER_NAME', 'HOSTNAME', 'HOST', 'NAME'),
        )
        ignore_logger('foxglove.bad_requests')
        logger.info('sentry initialised')
        return True
    else:
        logger.info('sentry not initialised')
        return False


def build_logging_config() -> Dict[str, Any]:
    """
    setup logging config by updating the arq logging config
    """
    log_level = glove.settings.log_level
    config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'foxglove.default': {
                '()': 'foxglove.logs.HighlightExtraFormatter',
                'fmt': '%(levelprefix)s %(message)s',
                'use_colors': None,
            },
            'foxglove.access': {
                '()': 'uvicorn.logging.AccessFormatter',
                'fmt': "%(levelprefix)s %(client_addr)s - '%(request_line)s' %(status_code)s",
            },
        },
        'handlers': {
            'foxglove.default': {
                'formatter': 'foxglove.default',
                'class': 'logging.StreamHandler',
                'stream': 'ext://sys.stderr',
                'level': log_level,
            },
            'foxglove.access': {
                'formatter': 'foxglove.access',
                'class': 'logging.StreamHandler',
                'stream': 'ext://sys.stdout',
                'level': log_level,
            },
        },
        'loggers': {
            '': {'handlers': ['foxglove.default'], 'level': log_level},
            'uvicorn.error': {'handlers': ['foxglove.default'], 'level': log_level, 'propagate': False},
            'uvicorn.access': {'handlers': ['foxglove.access'], 'level': log_level, 'propagate': False},
        },
    }
    return config


def setup_logging() -> None:
    config = build_logging_config()
    logging.config.dictConfig(config)
    setup_sentry()
