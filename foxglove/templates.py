import asyncio
from functools import wraps
from time import time
from typing import Optional, Any

from starlette.templating import Jinja2Templates as _Jinja2Templates

from .main import glove

try:
    import jinja2
except ImportError:  # pragma: nocover
    jinja2 = None  # type: ignore

reload_sha = 'f3c14fc6cf15e85950b3621be2ec879025738248'
reload_snippet = f'<script src="https://rawcdn.githack.com/samuelcolvin/foxglove/{reload_sha}/reload.js"></script>'


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
            url = request.url_for(context['static_route_name'], path=path)
            if context['dev_mode']:
                url += f'?t={time() * 1000:0.0f}'
            return url

        env = super().get_env(directory)
        env.globals.update(
            prompt_reload=prompt_reload,
            static_url=static_url,
            dev_mode=glove.settings.dev_mode,
            static_route_name='static',
        )
        return env

    def render(self, template_name: str):
        def view_decorator(view):
            if asyncio.iscoroutinefunction(view):
                @wraps(view)
                async def view_wrapper(request):
                    return self._return_template(request, template_name, await view(request))
            else:
                @wraps(view)
                def view_wrapper(request):
                    return self._return_template(request, template_name, view(request))
            return view_wrapper

        return view_decorator

    def _return_template(self, request, template_name: str, context: Optional[dict]):
        if context is None:
            context = {}
        context['request'] = request
        return self.TemplateResponse(template_name, context)
