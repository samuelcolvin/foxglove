import asyncio
import os
import secrets
from functools import wraps
from time import time
from typing import Optional, Tuple, Union

from starlette.responses import Response
from starlette.templating import Jinja2Templates as _Jinja2Templates, _TemplateResponse

from .main import glove

try:
    import jinja2
except ImportError:  # pragma: nocover
    jinja2 = None  # type: ignore

__all__ = 'FoxgloveTemplates', 'FoxgloveTestTemplates'

reload_sha = 'fbc87301a2470263e3ba45e56c7089f286a84a4e'
reload_snippet = f'<script src="https://rawcdn.githack.com/samuelcolvin/foxglove/{reload_sha}/reload.js"></script>'
static_version = (os.getenv('HEROKU_SLUG_COMMIT') or secrets.token_hex(4))[:7]


class FoxgloveTemplates(_Jinja2Templates):
    def __init__(self, directory: Optional[str] = None):
        super().__init__(glove.settings.template_dir if directory is None else directory)

    def get_env(self, directory: str) -> 'jinja2.Environment':
        @jinja2.contextfunction
        def prompt_reload(context: dict) -> str:
            if context['dev_mode']:
                return jinja2.Markup(reload_snippet)
            else:
                return ''

        @jinja2.contextfunction
        def static_url(context: dict, path: str) -> str:
            request = context['request']
            try:
                static_route_name = context.get('static_route_name', 'static')
                url = request.url_for(static_route_name, path=path)
                if context['dev_mode']:
                    url += f'?t={time() * 1000:0.0f}'
                else:
                    url += f'?v={static_version}'
                return url
            except KeyError:
                return f'/static/{path}'

        env = super().get_env(directory)
        env.globals.update(prompt_reload=prompt_reload, static_url=static_url, dev_mode=glove.settings.dev_mode)
        return env

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


class FoxgloveTestTemplates(FoxgloveTemplates):
    # from here on is just a hacky workaround for https://github.com/encode/starlette/issues/472
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
        return CustomTemplateResponse(
            template,
            context,
            status_code=status_code,
            headers=headers,
            media_type=media_type,
            background=background,
        )


class CustomTemplateResponse(_TemplateResponse):
    async def __call__(self, scope, receive, send) -> None:
        # context sending removed
        await Response.__call__(self, scope, receive, send)
