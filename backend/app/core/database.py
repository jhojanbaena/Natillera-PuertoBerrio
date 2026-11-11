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
    finanzas_columns = {column["name"] for column in inspect(engine).get_columns("finanzas_socio")}
    with engine.begin() as connection:
        for statement in finanzas_compat_sql(finanzas_columns):
            connection.execute(text(statement))


def finanzas_compat_sql(existing_columns: set[str]) -> list[str]:
    """DDL idempotente para aportes mensuales (periodo) y pagos vinculados a multas (multa_id)."""
    statements = []
    if "periodo" not in existing_columns:
        statements.append("ALTER TABLE finanzas_socio ADD COLUMN periodo VARCHAR(7)")
    if "multa_id" not in existing_columns:
        statements.append(
            "ALTER TABLE finanzas_socio ADD COLUMN multa_id INTEGER "
            "REFERENCES finanzas_socio(id) ON DELETE SET NULL"
        )
    statements += [
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_finanza_aporte_periodo "
        "ON finanzas_socio(socio_id, tipo_movimiento, periodo)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_finanza_pago_multa ON finanzas_socio(multa_id)",
    ]
    return statements
