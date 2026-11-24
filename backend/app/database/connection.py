from sqlalchemy import URL, create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


database_url = URL.create(
    drivername="postgresql+psycopg",
    username=settings.database_user,
    password=settings.database_password,
    host=settings.database_host,
    port=settings.database_port,
    database=settings.database_name,
)

engine = create_engine(
    database_url,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def test_database_connection():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT version()"))
        return result.scalar()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()