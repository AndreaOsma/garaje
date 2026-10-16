"""SQLAlchemy engine, session factory y dependencia `get_db` de FastAPI para Garaje."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool
import os
from dotenv import load_dotenv

load_dotenv()

# El bundle desktop fija DATABASE_URL antes de que este módulo cargue (vía desktop_launcher).
if os.getenv("GARAJE_DESKTOP", "").strip() in ("1", "true", "yes") and not os.getenv("DATABASE_URL"):
    from .desktop import configure_desktop_environment
    configure_desktop_environment()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

_is_memory_sqlite = DATABASE_URL == "sqlite:///:memory:"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    poolclass=StaticPool if _is_memory_sqlite else None,
)
if DATABASE_URL.startswith("sqlite"):
    # SQLite ignora ON DELETE CASCADE/SET NULL salvo que se active por conexión.
    @event.listens_for(engine, "connect")
    def _sqlite_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
