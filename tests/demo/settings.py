from pathlib import Path
from typing import List

from foxglove.settings import BaseSettings

THIS_DIR = Path(__file__).parent.resolve()


class Settings(BaseSettings):
    sql_path: Path = THIS_DIR / 'models.sql'
    patch_paths: List[str] = ['demo.patches']
