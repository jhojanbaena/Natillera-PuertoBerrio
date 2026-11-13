"""Configuración del motor ORM de Base de Datos y Sesiones con SQLAlchemy 2.0."""
from typing import Generator
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session, DeclarativeBase
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    hide_parameters=True,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=10,
    connect_args={"connect_timeout": 10},
)

# Fábrica de sesiones ORM
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


# Clase base declarativa SQLAlchemy 2.0
class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """
    Inyector de dependencia para FastAPI que provee una sesión de base de datos
    por petición HTTP y asegura su cierre al terminar.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ensure_compatibility_columns() -> None:
    """Añade columnas nuevas a instalaciones existentes sin perder datos."""
    columns = {column["name"] for column in inspect(engine).get_columns("notas")}
    if "fecha_programada" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE notas ADD COLUMN fecha_programada DATE"))
