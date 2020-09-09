from pathlib import Path

from foxglove.settings import BaseSettings

THIS_DIR = Path(__file__).parent.resolve()


class Settings(BaseSettings):
    sql_path: Path = THIS_DIR / 'models.sql'
