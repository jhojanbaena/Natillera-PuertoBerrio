"""Configuración del motor ORM de Base de Datos y Sesiones con SQLAlchemy 2.0."""
from typing import Generator
from fastapi import Request
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session, DeclarativeBase
from app.core.config import settings

# Tablas compartidas por todos los años (usuarios, periodos, límites de login)
# usan este esquema simbólico. Siempre se traduce al esquema real de la base
# (public en PostgreSQL), mientras que las tablas de cada año (sin esquema) se
# traducen al esquema del año que se consulta. Ver app/core/periodos.py.
SCHEMA_COMUN = "comun"
# Siempre las dos llaves: SQLAlchemy exige llaves consistentes entre mapas.
MAPA_ESQUEMAS_BASE = {None: None, SCHEMA_COMUN: None}

engine = create_engine(
    settings.DATABASE_URL,
    execution_options={"schema_translate_map": MAPA_ESQUEMAS_BASE},
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


def get_db(request: Request) -> Generator[Session, None, None]:
    """
    Inyector de dependencia para FastAPI que provee una sesión de base de datos
    por petición HTTP y asegura su cierre al terminar.

    La sesión queda ligada al año (periodo) que se consulta: el activo por
    defecto, o el indicado en la cabecera X-Periodo (solo lectura si no es el activo).
    """
    from app.core.periodos import configurar_periodo
    db = SessionLocal()
    try:
        configurar_periodo(db, request.headers.get("X-Periodo"))
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
    with engine.begin() as connection:
        for statement in prestamos_compat_sql(connection):
            connection.execute(text(statement))
        if connection.dialect.name == "postgresql":
            # SQLite no permite cambiar CHECK; en el demo basta con --reset.
            from app.core.integrity import CHECKS, OBSOLETE_CHECKS
            for table_name, names in OBSOLETE_CHECKS.items():
                for name in names:
                    connection.execute(text(f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{name}"'))
            for table_name, checks in CHECKS.items():
                existing = {c["name"] for c in inspect(connection).get_check_constraints(table_name)}
                for name, expression in checks.items():
                    if name not in existing:
                        connection.execute(text(f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{name}" CHECK ({expression})'))
    # Años: los datos existentes quedan registrados como el año en curso (sin moverlos).
    from app.core.periodos import asegurar_periodo_inicial
    with engine.begin() as connection:
        asegurar_periodo_inicial(connection)


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


def prestamos_compat_sql(connection) -> list[str]:
    """DDL idempotente para las reglas de interés 7 % / 10 % y 7 % / 3 %.

    Solo agrega columnas con valores por defecto: los préstamos y abonos
    existentes conservan sus valores (regla FIJA).
    """
    inspector = inspect(connection)
    prestamo_cols = {c["name"] for c in inspector.get_columns("prestamos")}
    abono_cols = {c["name"] for c in inspector.get_columns("abonos_prestamo")}
    nuevas_prestamo = {
        "regla_interes": "VARCHAR(20) NOT NULL DEFAULT 'FIJA'",
        "tasa_mora": "NUMERIC(5, 2)",
    }
    nuevas_abono = {
        "tasa_aplicada": "NUMERIC(5, 2)",
        "fecha_limite": "DATE",
        "dias_retraso": "INTEGER",
        "interes_bien_comun": "NUMERIC(12, 2)",
    }
    statements = [
        f"ALTER TABLE prestamos ADD COLUMN {nombre} {tipo}"
        for nombre, tipo in nuevas_prestamo.items() if nombre not in prestamo_cols
    ]
    statements += [
        f"ALTER TABLE abonos_prestamo ADD COLUMN {nombre} {tipo}"
        for nombre, tipo in nuevas_abono.items() if nombre not in abono_cols
    ]
    return statements
