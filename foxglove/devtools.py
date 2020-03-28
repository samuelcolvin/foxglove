import asyncio
import logging
from starlette.endpoints import WebSocketEndpoint
from starlette.routing import WebSocketRoute
from watchgod import awatch, DefaultWatcher

logger = logging.getLogger('foxglove.cli')


class IgnorePythonWatcher(DefaultWatcher):
    ignored_file_regexes = DefaultWatcher.ignored_file_regexes + (r'\.py$', r'\.pyx$', r'\.pyd$')


def reload_endpoint(watch_path: str):
    async def watch_reload(prompt_reload):
        async for _ in awatch(watch_path, watcher_cls=IgnorePythonWatcher):
            await prompt_reload()

    class ReloadWs(WebSocketEndpoint):
        encoding = 'text'

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._watch_task = asyncio.create_task(watch_reload(self.prompt_reload))
            self.ws = None

        async def prompt_reload(self):
            if self.ws:
                logger.debug('prompting reload')
                await self.ws.send_text('reload')

        async def on_connect(self, websocket):
            logger.debug('reload websocket connecting')
            await websocket.accept()
            self.ws = websocket

        async def on_disconnect(self, websocket, close_code):
            logger.debug('reload websocket disconnecting')
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                logger.debug('file watch cancelled')

    return WebSocketRoute('/.devtools/reload/', ReloadWs, name='devtools-reload')
