from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.config import get_database_url

engine = create_engine(
    get_database_url(),
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
