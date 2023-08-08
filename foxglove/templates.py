import asyncio
import os
import secrets
from functools import wraps
from time import time
from typing import Any, Optional, Tuple, Union

from starlette.responses import Response
from starlette.templating import Jinja2Templates as _Jinja2Templates, _TemplateResponse

from .main import glove

try:
    import jinja2
except ImportError:  # pragma: nocover
    jinja2 = None  # type: ignore

try:
    from markupsafe import Markup
except ImportError:  # pragma: nocover
    Markup = None  # type: ignore

__all__ = ('FoxgloveTemplates',)


class FoxgloveTemplates(_Jinja2Templates):
    def __init__(self, directory: Union[str, os.PathLike, None] = None, **env_options: Any) -> None:
        directory = glove.settings.template_dir if directory is None else directory
        super().__init__(directory, **env_options)
        self.env.globals.update(static_url=static_url, dev_mode=glove.settings.dev_mode)

    def render(self, template_name: str):
        def view_decorator(view):
            if asyncio.iscoroutinefunction(view):

                @wraps(view)
                async def view_wrapper(request, *args, **kwargs):
                    return self._return_template(request, template_name, await view(request, *args, **kwargs))

            else:

                @wraps(view)
                def view_wrapper(request, *args, **kwargs):
                    return self._return_template(request, template_name, view(request, *args, **kwargs))

            return view_wrapper

        return view_decorator

    def _return_template(self, request, template_name: str, r: Union[Optional[dict], Tuple[int, Optional[dict]]]):
        if isinstance(r, (tuple, list)):
            status_code, context = r
        else:
            status_code, context = 200, r
        if context is None:
            context = {}
        context['request'] = request
        return self.TemplateResponse(template_name, context, status_code=status_code)

    if glove.settings.test_mode:  # pragma: no branch
        # hacky workaround for https://github.com/encode/starlette/issues/472

        def TemplateResponse(
            self,
            name: str,
            context: dict,
            status_code: int = 200,
            headers: dict = None,
            media_type: str = None,
            background=None,
        ) -> _TemplateResponse:
            if 'request' not in context:
                raise ValueError('context must include a "request" key')
            template = self.get_template(name)
            return TestingTemplateResponse(
                template,
                context,
                status_code=status_code,
                headers=headers,
                media_type=media_type,
                background=background,
            )


static_version = (glove.settings.release or secrets.token_hex(4))[:7]


@jinja2.pass_context
def static_url(context: dict, path: str) -> str:
    request = context['request']
    try:
        static_route_name = context.get('static_route_name', 'static')
        url = str(request.url_for(static_route_name, path=path))
        if context['dev_mode']:
            url += f'?t={time() * 1000:0.0f}'
        else:
            url += f'?v={static_version}'
        return url
    except KeyError:
        return f'/static/{path}'


class TestingTemplateResponse(_TemplateResponse):
    """
    See https://github.com/encode/starlette/issues/472. Alternative for _TemplateResponse that avoids
    `send(..."type": "http.response.template"...)` and thus works while testing.
    """

    async def __call__(self, scope, receive, send) -> None:
        # context sending removed
        await Response.__call__(self, scope, receive, send)
