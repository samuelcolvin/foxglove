from typing import Dict

from buildpg.asyncpg import BuildPgConnection

from foxglove.db.patches import patch


@patch
async def check_args(conn: BuildPgConnection, args: Dict[str, str], logger, **kwargs):
    """
    check args are working right
    """
    logger.info('checking args: %s', args)
    assert args == {'user_id': '123', 'co': 'Testing'}
    assert await conn.fetchval('select 4^4') == 256
