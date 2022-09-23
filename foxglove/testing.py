"""
Client for testing, this is mostly copied from starlette 0.14.2

https://github.com/encode/starlette/blob/0.14.2/starlette/testclient.py

After that the standard test client for starlette started using threads to run the server and therefore
broke support for a database connection shared between the test code and the application code.
"""
import asyncio
import http
import inspect
import io
import json
import queue
import threading
import types
from typing import IO, Any, Awaitable, Callable, Dict, List, MutableMapping, Optional, Sequence, Tuple, Union, cast
from urllib.parse import unquote, urljoin, urlsplit

from requests import PreparedRequest, Response
from requests.adapters import HTTPAdapter
from requests.auth import AuthBase
from requests.cookies import RequestsCookieJar
from requests.packages.urllib3._collections import HTTPHeaderDict

try:
    from devtools.prettier import pformat
except ImportError:
    from pprint import pformat

try:
    import pytest
except ImportError:
    pytest = None

import requests
from starlette.types import Message, Receive, Scope, Send
from starlette.websockets import WebSocketDisconnect

# Annotations for `Session.request()`
Cookies = Union[MutableMapping[str, str], RequestsCookieJar]
Params = Union[bytes, MutableMapping[str, str]]
DataType = Union[bytes, MutableMapping[str, str], IO]
TimeOut = Union[float, Tuple[float, float]]
FileType = MutableMapping[str, IO]
AuthType = Union[
    Tuple[str, str],
    AuthBase,
    Callable[[requests.Request], requests.Request],
]


ASGIInstance = Callable[[Receive, Send], Awaitable[None]]
ASGI2App = Callable[[Scope], ASGIInstance]
ASGI3App = Callable[[Scope, Receive, Send], Awaitable[None]]


class _HeaderDict(HTTPHeaderDict):
    def get_all(self, key: str, default: str) -> str:
        return self.getheaders(key)


class _MockOriginalResponse:
    """
    We have to jump through some hoops to present the response as if
    it was made using urllib3.
    """

    def __init__(self, headers: List[Tuple[bytes, bytes]]) -> None:
        self.msg = _HeaderDict(headers)
        self.closed = False

    def isclosed(self) -> bool:
        return self.closed


class _Upgrade(Exception):
    def __init__(self, session: 'WebSocketTestSession') -> None:
        self.session = session


def _get_reason_phrase(status_code: int) -> str:
    try:
        return http.HTTPStatus(status_code).phrase
    except ValueError:
        return ''


def _is_asgi3(app: Union[ASGI2App, ASGI3App]) -> bool:
    if inspect.isclass(app):
        return hasattr(app, '__await__')
    elif inspect.isfunction(app):
        return asyncio.iscoroutinefunction(app)
    call = getattr(app, '__call__', None)
    return asyncio.iscoroutinefunction(call)


class _WrapASGI2:
    """
    Provide an ASGI3 interface onto an ASGI2 app.
    """

    def __init__(self, app: ASGI2App) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        instance = self.app(scope)
        await instance(receive, send)


class _ASGIAdapter(HTTPAdapter):
    def __init__(
        self,
        app: ASGI3App,
        raise_server_exceptions: bool = True,
        root_path: str = '',
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self.app = app
        self.raise_server_exceptions = raise_server_exceptions
        self.root_path = root_path
        self.loop = loop or asyncio.get_event_loop()

    def send(self, request: PreparedRequest, *args: Any, **kwargs: Any) -> Response:  # noqa: C901
        scheme, netloc, path, query, fragment = (str(item) for item in urlsplit(request.url))

        default_port = {'http': 80, 'ws': 80, 'https': 443, 'wss': 443}[scheme]

        if ':' in netloc:
            host, port_string = netloc.split(':', 1)
            port = int(port_string)
        else:
            host = netloc
            port = default_port

        # Include the 'host' header.
        if 'host' in request.headers:
            headers: List[Tuple[bytes, bytes]] = []
        elif port == default_port:
            headers = [(b'host', host.encode())]
        else:
            headers = [(b'host', (f'{host}:{port}').encode())]

        # Include other request headers.
        headers += [(key.lower().encode(), value.encode()) for key, value in request.headers.items()]

        if scheme in {'ws', 'wss'}:
            subprotocol = request.headers.get('sec-websocket-protocol', None)
            if subprotocol is None:
                subprotocols: Sequence[str] = []
            else:
                subprotocols = [value.strip() for value in subprotocol.split(',')]
            scope = {
                'type': 'websocket',
                'path': unquote(path),
                'root_path': self.root_path,
                'scheme': scheme,
                'query_string': query.encode(),
                'headers': headers,
                'client': ['testclient', 50000],
                'server': [host, port],
                'subprotocols': subprotocols,
            }
            session = WebSocketTestSession(self.app, scope)
            raise _Upgrade(session)

        scope = {
            'type': 'http',
            'http_version': '1.1',
            'method': request.method,
            'path': unquote(path),
            'root_path': self.root_path,
            'scheme': scheme,
            'query_string': query.encode(),
            'headers': headers,
            'client': ['testclient', 50000],
            'server': [host, port],
            'extensions': {'http.response.template': {}},
        }

        request_complete = False
        response_started = False
        response_complete = False
        raw_kwargs: Dict[str, Any] = {'body': io.BytesIO()}
        template = None
        context = None

        async def receive() -> Message:
            nonlocal request_complete, response_complete

            if request_complete:
                while not response_complete:
                    await asyncio.sleep(0.0001)
                return {'type': 'http.disconnect'}

            body = request.body
            if isinstance(body, str):
                body_bytes: bytes = body.encode('utf-8')
            elif body is None:
                body_bytes = b''
            elif isinstance(body, types.GeneratorType):
                try:
                    chunk = body.send(None)
                    if isinstance(chunk, str):
                        chunk = chunk.encode('utf-8')
                    return {'type': 'http.request', 'body': chunk, 'more_body': True}
                except StopIteration:
                    request_complete = True
                    return {'type': 'http.request', 'body': b''}
            else:
                body_bytes = body

            request_complete = True
            return {'type': 'http.request', 'body': body_bytes}

        async def send(message: Message) -> None:
            nonlocal raw_kwargs, response_started, response_complete, template, context

            if message['type'] == 'http.response.start':
                assert not response_started, 'Received multiple "http.response.start" messages.'
                raw_kwargs['version'] = 11
                raw_kwargs['status'] = message['status']
                raw_kwargs['reason'] = _get_reason_phrase(message['status'])
                raw_kwargs['headers'] = [(key.decode(), value.decode()) for key, value in message['headers']]
                raw_kwargs['preload_content'] = False
                raw_kwargs['original_response'] = _MockOriginalResponse(raw_kwargs['headers'])
                response_started = True
            elif message['type'] == 'http.response.body':
                assert response_started, 'Received "http.response.body" without "http.response.start".'
                assert not response_complete, 'Received "http.response.body" after response completed.'
                body = message.get('body', b'')
                more_body = message.get('more_body', False)
                if request.method != 'HEAD':
                    raw_kwargs['body'].write(body)
                if not more_body:
                    raw_kwargs['body'].seek(0)
                    response_complete = True
            elif message['type'] == 'http.response.template':
                template = message['template']
                context = message['context']

        try:
            self.loop.run_until_complete(self.app(scope, receive, send))
        except BaseException as exc:
            if self.raise_server_exceptions:
                raise exc from None

        if self.raise_server_exceptions:
            assert response_started, 'TestClient did not receive any response.'
        elif not response_started:
            raw_kwargs = {
                'version': 11,
                'status': 500,
                'reason': 'Internal Server Error',
                'headers': [],
                'preload_content': False,
                'original_response': _MockOriginalResponse([]),
                'body': io.BytesIO(),
            }

        raw = requests.packages.urllib3.HTTPResponse(**raw_kwargs)
        response = self.build_response(request, raw)
        if template is not None:
            response.template = template
            response.context = context
        return response


class WebSocketTestSession:
    def __init__(self, app: ASGI3App, scope: Scope) -> None:
        self.app = app
        self.scope = scope
        self.accepted_subprotocol = None
        self._receive_queue = queue.Queue()
        self._send_queue = queue.Queue()
        self._thread = threading.Thread(target=self._run)
        self.send({'type': 'websocket.connect'})
        self._thread.start()
        message = self.receive()
        self._raise_on_close(message)
        self.accepted_subprotocol = message.get('subprotocol', None)

    def __enter__(self) -> 'WebSocketTestSession':
        return self

    def __exit__(self, *args: Any) -> None:
        self.close(1000)
        self._thread.join()
        while not self._send_queue.empty():
            message = self._send_queue.get()
            if isinstance(message, BaseException):
                raise message

    def _run(self) -> None:
        """
        The sub-thread in which the websocket session runs.
        """
        loop = asyncio.new_event_loop()
        scope = self.scope
        receive = self._asgi_receive
        send = self._asgi_send
        try:
            loop.run_until_complete(self.app(scope, receive, send))
        except BaseException as exc:
            self._send_queue.put(exc)
        finally:
            loop.close()

    async def _asgi_receive(self) -> Message:
        while self._receive_queue.empty():
            await asyncio.sleep(0)
        return self._receive_queue.get()

    async def _asgi_send(self, message: Message) -> None:
        self._send_queue.put(message)

    def _raise_on_close(self, message: Message) -> None:
        if message['type'] == 'websocket.close':
            raise WebSocketDisconnect(message.get('code', 1000))

    def send(self, message: Message) -> None:
        self._receive_queue.put(message)

    def send_text(self, data: str) -> None:
        self.send({'type': 'websocket.receive', 'text': data})

    def send_bytes(self, data: bytes) -> None:
        self.send({'type': 'websocket.receive', 'bytes': data})

    def send_json(self, data: Any, mode: str = 'text') -> None:
        assert mode in ['text', 'binary']
        text = json.dumps(data)
        if mode == 'text':
            self.send({'type': 'websocket.receive', 'text': text})
        else:
            self.send({'type': 'websocket.receive', 'bytes': text.encode('utf-8')})

    def close(self, code: int = 1000) -> None:
        self.send({'type': 'websocket.disconnect', 'code': code})

    def receive(self) -> Message:
        message = self._send_queue.get()
        if isinstance(message, BaseException):
            raise message
        return message

    def receive_text(self) -> str:
        message = self.receive()
        self._raise_on_close(message)
        return message['text']

    def receive_bytes(self) -> bytes:
        message = self.receive()
        self._raise_on_close(message)
        return message['bytes']

    def receive_json(self, mode: str = 'text') -> Any:
        assert mode in ['text', 'binary']
        message = self.receive()
        self._raise_on_close(message)
        if mode == 'text':
            text = message['text']
        else:
            text = message['bytes'].decode('utf-8')
        return json.loads(text)


class TestClient(requests.Session):
    __test__ = False  # For pytest to not discover this up.

    def __init__(
        self,
        app: ASGI3App,
        base_url: str = 'http://testserver',
        raise_server_exceptions: bool = True,
        root_path: str = '',
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        super().__init__()
        assert _is_asgi3(app), f'{app} is not an ASGI3 app'
        if _is_asgi3(app):
            app = cast(ASGI3App, app)
            asgi_app = app
        else:
            app = cast(ASGI2App, app)
            asgi_app = _WrapASGI2(app)

        self.loop = loop or asyncio.get_event_loop()
        adapter = _ASGIAdapter(
            asgi_app,
            raise_server_exceptions=raise_server_exceptions,
            root_path=root_path,
            loop=self.loop,
        )
        self.mount('http://', adapter)
        self.mount('https://', adapter)
        self.mount('ws://', adapter)
        self.mount('wss://', adapter)
        self.headers.update({'user-agent': 'testclient'})
        self.app = asgi_app
        self.base_url = base_url
        self.last_response: Optional[Response] = None

    def request(  # type: ignore
        self,
        method: str,
        url: str,
        params: Params = None,
        data: DataType = None,
        headers: MutableMapping[str, str] = None,
        cookies: Cookies = None,
        files: FileType = None,
        auth: AuthType = None,
        timeout: TimeOut = None,
        allow_redirects: bool = None,
        proxies: MutableMapping[str, str] = None,
        hooks: Any = None,
        stream: bool = None,
        verify: Union[bool, str] = None,
        cert: Union[str, Tuple[str, str]] = None,
        json: Any = None,
    ) -> Response:
        url = urljoin(self.base_url, url)
        self.last_response = r = super().request(
            method,
            url,
            params=params,
            data=data,
            headers=headers,
            cookies=cookies,
            files=files,
            auth=auth,
            timeout=timeout,
            allow_redirects=allow_redirects,
            proxies=proxies,
            hooks=hooks,
            stream=stream,
            verify=verify,
            cert=cert,
            json=json,
        )
        return r

    def websocket_connect(self, url: str, subprotocols: Sequence[str] = None, **kwargs: Any) -> Any:
        url = urljoin('ws://testserver', url)
        headers = kwargs.get('headers', {})
        headers.setdefault('connection', 'upgrade')
        headers.setdefault('sec-websocket-key', 'testserver==')
        headers.setdefault('sec-websocket-version', '13')
        if subprotocols is not None:
            headers.setdefault('sec-websocket-protocol', ', '.join(subprotocols))
        kwargs['headers'] = headers
        try:
            super().request('GET', url, **kwargs)
        except _Upgrade as exc:
            session = exc.session
        else:
            raise RuntimeError('Expected WebSocket upgrade')  # pragma: no cover

        return session

    def __enter__(self) -> 'TestClient':
        self.send_queue = asyncio.Queue()
        self.receive_queue = asyncio.Queue()
        self.task = self.loop.create_task(self.lifespan())
        self.loop.run_until_complete(self.wait_startup())
        return self

    def __exit__(self, *args: Any) -> None:
        self.loop.run_until_complete(self.wait_shutdown())

    async def lifespan(self) -> None:
        scope = {'type': 'lifespan'}
        try:
            await self.app(scope, self.receive_queue.get, self.send_queue.put)
        finally:
            await self.send_queue.put(None)

    async def wait_startup(self) -> None:
        await self.receive_queue.put({'type': 'lifespan.startup'})
        message = await self.send_queue.get()
        if message is None:
            self.task.result()
        assert message['type'] in (
            'lifespan.startup.complete',
            'lifespan.startup.failed',
        )
        if message['type'] == 'lifespan.startup.failed':
            message = await self.send_queue.get()
            if message is None:
                self.task.result()

    async def wait_shutdown(self) -> None:
        await self.receive_queue.put({'type': 'lifespan.shutdown'})
        message = await self.send_queue.get()
        if message is None:
            self.task.result()
        assert message['type'] == 'lifespan.shutdown.complete'
        await self.task

    def get_json(
        self,
        url: str,
        *,
        allow_redirects: bool = False,
        status: Optional[int] = 200,
        headers: Dict[str, str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        r = self.get(url, allow_redirects=allow_redirects, headers=headers, **kwargs)
        check_response(r, status)
        return r.json()

    def post_json(
        self,
        url: str,
        json: Any = None,
        *,
        allow_redirects: bool = False,
        status: Optional[int] = 200,
        headers: Dict[str, str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        r = self.post(url, json=json, allow_redirects=allow_redirects, headers=headers, **kwargs)
        check_response(r, status)
        return r.json()


def check_response(response: Response, expected_status: Optional[int]) -> None:
    if expected_status is None or response.status_code == expected_status:
        return

    try:
        body = pformat(response.json())
    except ValueError:
        body = response.text

    req = response.request
    msg = (
        f'{req.method} {req.url} returned unexpected status: {response.status_code} (expected {expected_status}), '
        f'body:\n{body}'
    )

    if pytest:  # pragma: no branch
        pytest.fail(msg)
    else:  # pragma: no cover
        raise ValueError(msg)
