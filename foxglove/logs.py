import logging
import logging.config
import os
import traceback
from io import StringIO
from typing import Any, Dict

try:
    import pygments
    from pygments.lexers import Python3TracebackLexer
    from pygments.formatters import Terminal256Formatter
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
}


class HighlightStreamHandler(logging.StreamHandler):
    def setFormatter(self, fmt):
        self.formatter = fmt
        self.formatter.stream_is_tty = isatty and isatty(self.stream)


class HighlightExtraFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        self.stream_is_tty = False

    def formatMessage(self, record):
        s = super().formatMessage(record)
        extra = {k: v for k, v in record.__dict__.items() if k not in standard_record_keys}
        if extra:
            s += '\nExtra: ' + format_extra(extra, highlight=self.stream_is_tty)
        return s

    def formatException(self, ei):
        sio = StringIO()
        traceback.print_exception(*ei, file=sio)
        stack = sio.getvalue()
        sio.close()
        if self.stream_is_tty and pyg_lexer:
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


def build_logging_config(debug: bool, disable_existing: bool, main_logger_name: str) -> Dict[str, Any]:
    """
    setup logging config by updating the arq logging config
    """
    log_level = 'DEBUG' if debug else 'INFO'
    sentry_dsn = os.getenv('SENTRY_DSN', None)
    if sentry_dsn in ('', '-'):
        # thus setting an environment variable of "-" means no sentry
        sentry_dsn = None

    if sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration, ignore_logger

        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[LoggingIntegration(level=logging.INFO, event_level=logging.WARNING)],
            release=get_env_multiple('COMMIT', 'RELEASE'),
            server_name=get_env_multiple('DYNO', 'SERVER_NAME', 'HOSTNAME', 'HOST', 'NAME'),
        )
        ignore_logger('foxglove.middleware')
        warning_handler = {'level': 'WARNING', 'class': 'logging.NullHandler'}
        default_filters = []
    else:
        warning_handler = {
            'level': 'WARNING',
            'class': 'foxglove.logs.HighlightStreamHandler',
            'formatter': 'foxglove.highlighted_formatter',
        }
        # we don't print above warnings on foxglove.default to avoid duplicate errors in the console
        default_filters = ['not_warnings']

    config = {
        'version': 1,
        'disable_existing_loggers': disable_existing,
        'formatters': {
            'foxglove.simple_formatter': {'format': '%(message)s'},
            'foxglove.default_formatter': {'format': '%(levelname)-7s %(name)19s: %(message)s'},
            'foxglove.highlighted_formatter': {'class': 'foxglove.logs.HighlightExtraFormatter'},
        },
        'filters': {'not_warnings': {'()': 'foxglove.logs.NotWarnings'}},
        'handlers': {
            'foxglove.simple': {
                'level': log_level,
                'class': 'logging.StreamHandler',
                'formatter': 'foxglove.simple_formatter',
            },
            'foxglove.default': {
                'level': log_level,
                'class': 'logging.StreamHandler',
                'formatter': 'foxglove.default_formatter',
                'filters': default_filters,
            },
            'foxglove.warning': warning_handler,
        },
        'loggers': {
            'foxglove': {'handlers': ['foxglove.default', 'foxglove.warning'], 'level': log_level},
            'foxglove.access': {'handlers': ['foxglove.simple'], 'level': log_level, 'propagate': False},
            main_logger_name: {'handlers': ['foxglove.default', 'foxglove.warning'], 'level': log_level},
            'arq': {'handlers': ['foxglove.default', 'foxglove.warning'], 'level': log_level},
        },
    }
    return config


def setup_logging(debug: bool = False, disable_existing: bool = False, main_logger_name: str = 'app') -> None:
    config = build_logging_config(debug, disable_existing, main_logger_name)
    logging.config.dictConfig(config)
