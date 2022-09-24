import pytest
from dirty_equals import IsStr

from foxglove.testing import TestClient as Client


def test_template(client: Client):
    r = client.get('/template/')
    assert r.status_code == 200, r.text
    assert r.headers['content-type'] == 'text/html; charset=utf-8'
    assert r.text == '<p>Hello Samuel</p>'


def test_template_status(client: Client):
    r = client.get('/template/456/')
    assert r.status_code == 456, r.text
    assert r.headers['content-type'] == 'text/html; charset=utf-8'
    assert r.text == '<p>Hello ???</p>'


def test_template_static_url(client: Client):
    r = client.get('/template/spam/')
    assert r.status_code == 200, r.text
    assert r.headers['content-type'] == 'text/html; charset=utf-8'
    assert r.text == IsStr(regex=r'<script src="http://testserver/static/foobar\.js\?v=[0-9a-f]{7}"></script>')


def test_no_request(glove):
    from foxglove.templates import FoxgloveTemplates

    templates = FoxgloveTemplates()
    with pytest.raises(ValueError, match='context must include a "request" key'):
        templates.TemplateResponse('foobar', {})
