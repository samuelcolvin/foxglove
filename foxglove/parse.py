from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError
from starlette.requests import Request

from . import exceptions

PydanticModel = TypeVar('PydanticModel', bound=BaseModel)


async def parse_request_body(request: Request, model: Type[PydanticModel], *, error_headers=None) -> PydanticModel:
    error_details = None
    content_type = request.headers.get('content-type')
    data_format = 'JSON'
    try:
        if content_type == 'application/x-www-form-urlencoded':
            data_format = 'form-encoded'
            data = await request.form()
        else:
            data = await request.json()
    except ValueError:
        error_msg = f'Invalid {data_format} data'
    else:
        try:
            return model.parse_obj(data)
        except ValidationError as e:
            error_msg = 'Invalid Data'
            error_details = e.errors()

    raise exceptions.HttpBadRequest(message=error_msg, details=error_details, headers=error_headers)
