from pathlib import Path
from typing import List, Optional

from arq.connections import RedisSettings

from foxglove.settings import BaseSettings

THIS_DIR = Path(__file__).parent.resolve()


class Settings(BaseSettings):
    sql_path: Path = THIS_DIR / 'models.sql'
    patch_paths: List[str] = ['demo.patches']
    pg_dsn = 'postgres://postgres@localhost:5432/foxglove_demo'
    app = 'demo.main:app'
    redis_settings: Optional[RedisSettings] = 'redis://localhost:6379/6'
    template_dir = THIS_DIR / 'templates'
    static = THIS_DIR / 'static'

    worker_func = 'demo.main:worker'
