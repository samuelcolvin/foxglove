import pytest

from foxglove.testing import Client


@pytest.mark.filterwarnings('ignore::DeprecationWarning:starlette.templating')
def test_render_template(client: Client):
    r = client.get('/render-template/')
    assert r.status_code == 200, r.text
    # assert  == {'app': 'foxglove-demo'}
