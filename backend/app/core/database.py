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
        liquidacion_metodo_opcional(connection)
        for statement in actividades_socio_compat_sql(connection):
            connection.execute(text(statement))
        if connection.dialect.name == "sqlite":
            from app.core.periodos import _adjuntar_sqlite
            _adjuntar_sqlite(connection.connection.dbapi_connection, esquemas_de_anios(connection))
        compat_esquemas_de_anios(connection)
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


def prestamos_compat_sql(connection, schema: str | None = None) -> list[str]:
    """DDL idempotente para las reglas de interés 7 % / 10 % y 7 % / 3 %.

    Solo agrega columnas con valores por defecto: los préstamos y abonos
    existentes conservan sus valores (regla FIJA). `orden_socio` queda NULL en
    los préstamos existentes, que así conservan su distribución de intereses.
    Con `schema` se aplica a las tablas de un año (periodo_AAAA).
    """
    inspector = inspect(connection)
    prestamo_cols = {c["name"] for c in inspector.get_columns("prestamos", schema=schema)}
    abono_cols = {c["name"] for c in inspector.get_columns("abonos_prestamo", schema=schema)}
    prefijo = f'"{schema}".' if schema else ""
    nuevas_prestamo = {
        "regla_interes": "VARCHAR(20) NOT NULL DEFAULT 'FIJA'",
        "tasa_mora": "NUMERIC(5, 2)",
        "orden_socio": "INTEGER",
    }
    nuevas_abono = {
        "tasa_aplicada": "NUMERIC(5, 2)",
        "fecha_limite": "DATE",
        "dias_retraso": "INTEGER",
        "interes_bien_comun": "NUMERIC(12, 2)",
    }
    statements = [
        f"ALTER TABLE {prefijo}prestamos ADD COLUMN {nombre} {tipo}"
        for nombre, tipo in nuevas_prestamo.items() if nombre not in prestamo_cols
    ]
    statements += [
        f"ALTER TABLE {prefijo}abonos_prestamo ADD COLUMN {nombre} {tipo}"
        for nombre, tipo in nuevas_abono.items() if nombre not in abono_cols
    ]
    return statements


def actividades_socio_compat_sql(connection, schema: str | None = None) -> list[str]:
    """Columnas tipo y mes de las actividades del socio (las líneas existentes quedan como OTRA)."""
    inspector = inspect(connection)
    if not inspector.has_table("actividades_socio", schema=schema):
        return []
    columnas = {c["name"] for c in inspector.get_columns("actividades_socio", schema=schema)}
    prefijo = f'"{schema}".' if schema else ""
    nuevas = {"tipo": "VARCHAR(20) NOT NULL DEFAULT 'OTRA'", "mes": "INTEGER"}
    return [
        f"ALTER TABLE {prefijo}actividades_socio ADD COLUMN {nombre} {tipo}"
        for nombre, tipo in nuevas.items() if nombre not in columnas
    ]


def esquemas_de_anios(connection) -> list[str]:
    """Esquemas de los años creados con el apartado Años (vacío si aún no hay)."""
    try:
        filas = connection.execute(text("SELECT esquema FROM periodos WHERE esquema IS NOT NULL")).all()
    except Exception:  # Tabla de periodos aún no creada.
        return []
    import re
    return [fila[0] for fila in filas if fila[0] and re.match(r"^[a-z_][a-z0-9_]{0,62}$", fila[0])]


def liquidacion_metodo_opcional(connection, schema: str | None = None) -> None:
    """Permite liquidar sin método de pago (botón "Ya se liquidó").

    Los pagos existentes conservan su método; solo se quita el NOT NULL.
    """
    inspector = inspect(connection)
    if not inspector.has_table("liquidacion_pagos", schema=schema):
        return
    columna = next((c for c in inspector.get_columns("liquidacion_pagos", schema=schema)
                    if c["name"] == "metodo_pago"), None)
    if columna is None or columna.get("nullable", True):
        return
    prefijo = f'"{schema}".' if schema else ""
    if connection.dialect.name == "postgresql":
        connection.execute(text(f"ALTER TABLE {prefijo}liquidacion_pagos ALTER COLUMN metodo_pago DROP NOT NULL"))
        return
    # SQLite (modo demo/pruebas) no permite quitar NOT NULL: se reconstruye la tabla
    # copiando todas las filas, con el procedimiento recomendado por SQLite.
    maestro = f'"{schema}".sqlite_master' if schema else "sqlite_master"
    sql_tabla = connection.execute(text(
        f"SELECT sql FROM {maestro} WHERE type = 'table' AND name = 'liquidacion_pagos'"
    )).scalar_one()
    sql_indices = [fila[0] for fila in connection.execute(text(
        f"SELECT sql FROM {maestro} WHERE type = 'index' AND tbl_name = 'liquidacion_pagos' AND sql IS NOT NULL"
    )).all()]
    import re
    nuevo_sql = re.sub(r"(metodo_pago\s+VARCHAR\(20\))\s+NOT NULL", r"\1", sql_tabla, count=1, flags=re.IGNORECASE)
    nuevo_sql = re.sub(r"CREATE TABLE\s+\"?liquidacion_pagos\"?", f"CREATE TABLE {prefijo}liquidacion_pagos_nueva",
                       nuevo_sql, count=1, flags=re.IGNORECASE)
    connection.execute(text(nuevo_sql))
    connection.execute(text(f"INSERT INTO {prefijo}liquidacion_pagos_nueva SELECT * FROM {prefijo}liquidacion_pagos"))
    connection.execute(text(f"DROP TABLE {prefijo}liquidacion_pagos"))
    connection.execute(text(f"ALTER TABLE {prefijo}liquidacion_pagos_nueva RENAME TO liquidacion_pagos"))
    for sql_indice in sql_indices:
        if schema:
            sql_indice = re.sub(r"(CREATE (?:UNIQUE )?INDEX\s+)", rf'\1"{schema}".', sql_indice, count=1, flags=re.IGNORECASE)
        connection.execute(text(sql_indice))


def compat_esquemas_de_anios(connection) -> None:
    """Aplica las columnas y tablas nuevas también a las tablas de cada año creado."""
    from app.models.actividad_socio import ActividadSocio

    for esquema in esquemas_de_anios(connection):
        for statement in prestamos_compat_sql(connection, esquema):
            connection.execute(text(statement))
        liquidacion_metodo_opcional(connection, esquema)
        if not inspect(connection).has_table(ActividadSocio.__tablename__, schema=esquema):
            # Tabla nueva del año: se crea con el mismo mapeo de esquemas que usa Años.
            mapa_previo = connection.get_execution_options().get("schema_translate_map") or MAPA_ESQUEMAS_BASE
            connection.execution_options(schema_translate_map={
                None: esquema, SCHEMA_COMUN: mapa_previo.get(SCHEMA_COMUN),
            })
            try:
                ActividadSocio.__table__.create(connection, checkfirst=False)
            finally:
                connection.execution_options(schema_translate_map=mapa_previo)
        for statement in actividades_socio_compat_sql(connection, esquema):
            connection.execute(text(statement))
