from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from .settings import settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]

database_url = settings.database_url
if database_url.startswith('sqlite:///./'):
    rel = database_url.replace('sqlite:///./', '', 1)
    db_path = PROJECT_ROOT / rel
    db_path.parent.mkdir(parents=True, exist_ok=True)
    database_url = f'sqlite:///{db_path}'
elif database_url.startswith('sqlite:///'):
    raw = database_url.replace('sqlite:///', '', 1)
    db_path = Path(raw)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / raw
    db_path.parent.mkdir(parents=True, exist_ok=True)
    database_url = f'sqlite:///{db_path}'

connect_args = {'check_same_thread': False} if database_url.startswith('sqlite') else {}
engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
