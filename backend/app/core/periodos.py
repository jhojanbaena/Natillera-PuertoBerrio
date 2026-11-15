"""Periodos anuales de la natillera: cada año con sus propios datos.

Cómo funciona
-------------
- Las tablas compartidas (usuarios, periodos, límites de login) viven en el
  esquema simbólico SCHEMA_COMUN, que siempre apunta al esquema real de la base.
- Las demás tablas (socios, aportes, multas, préstamos, abonos, actividades,
  rifas, reuniones, notas, historial, gastos, contabilidad y liquidación) existen
  una vez por año:
    * el año original (2026) usa el esquema de siempre (esquema NULL en la tabla
      periodos), así la actualización no mueve ni borra ningún registro;
    * cada año nuevo se crea en un esquema propio ("periodo_2027", ...).
- Cada petición HTTP liga su sesión al año activo, o al año pedido en la
  cabecera X-Periodo. Todas las consultas e inserciones del sistema quedan así
  dentro del año correcto sin mezclar cálculos entre años.
- Un año que no es el activo es de solo consulta: cualquier intento de guardar,
  editar o borrar registros suyos se rechaza (HTTP 403).

En SQLite (pruebas y modo demo) cada año es una base adjunta (ATTACH) con el
mismo nombre del esquema.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import case, event, func, insert, inspect as sa_inspect, select, text, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import Base, SCHEMA_COMUN
from app.models.periodo import Periodo

ESQUEMA_VALIDO = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_TABLA_PERIODOS = Periodo.__table__


class PeriodoSoloLectura(Exception):
    """Se intentó modificar un año que no es el activo."""

    def __init__(self, anio: Optional[int]):
        self.anio = anio
        super().__init__(
            f"El año {anio} es de solo consulta. Para registrar o modificar información "
            "regresa al año activo desde el apartado Años."
        )


# ---------------------------------------------------------------------------
# Esquemas y motores por año
# ---------------------------------------------------------------------------

def _destino_base(engine: Engine) -> Optional[str]:
    """Esquema real de las tablas compartidas (None = el predeterminado de la base)."""
    mapa = engine.get_execution_options().get("schema_translate_map") or {}
    return mapa.get(SCHEMA_COMUN, mapa.get(None))


def mapa_esquemas(engine: Engine, esquema: Optional[str]) -> dict:
    base = _destino_base(engine)
    return {SCHEMA_COMUN: base, None: esquema or base}


def motor_periodo(engine: Engine, esquema: Optional[str]) -> Engine:
    """Motor que comparte el pool del base pero apunta las tablas del año a su esquema."""
    return engine.execution_options(schema_translate_map=mapa_esquemas(engine, esquema))


def nombre_esquema(engine: Engine, anio: int) -> str:
    base = _destino_base(engine)
    nombre = f"{base}_periodo_{anio}" if base else f"periodo_{anio}"
    if not ESQUEMA_VALIDO.match(nombre):
        raise ValueError("Nombre de esquema inválido")
    return nombre


def tablas_de_periodo() -> list:
    """Tablas que cada año tiene por separado (todas menos las compartidas)."""
    return [t for t in Base.metadata.sorted_tables if t.schema != SCHEMA_COMUN]


# ---------------------------------------------------------------------------
# SQLite: cada año es una base adjunta
# ---------------------------------------------------------------------------

def _archivo_sqlite(dbapi_conn, esquema: str) -> str:
    principal = next((fila[2] for fila in dbapi_conn.execute("PRAGMA database_list") if fila[1] == "main"), "")
    if not principal:
        return ":memory:"
    ruta = Path(principal)
    return str(ruta.with_name(f"{ruta.stem}_{esquema}{ruta.suffix or '.sqlite'}"))


def _adjuntar_sqlite(dbapi_conn, esquemas) -> None:
    adjuntas = {fila[1] for fila in dbapi_conn.execute("PRAGMA database_list")}
    for esquema in esquemas:
        if esquema and esquema not in adjuntas and ESQUEMA_VALIDO.match(esquema):
            dbapi_conn.execute(f'ATTACH DATABASE ? AS "{esquema}"', (_archivo_sqlite(dbapi_conn, esquema),))


def _preparar_sqlite(engine: Engine) -> None:
    if engine.dialect.name != "sqlite" or getattr(engine.pool, "_natillera_periodos", False):
        return

    def _al_tomar_conexion(dbapi_conn, _record, _proxy):
        try:
            esquemas = [fila[0] for fila in dbapi_conn.execute(
                "SELECT esquema FROM periodos WHERE esquema IS NOT NULL"
            )]
        except Exception:  # Tabla aún no creada.
            return
        _adjuntar_sqlite(dbapi_conn, esquemas)

    event.listen(engine.pool, "checkout", _al_tomar_conexion)
    engine.pool._natillera_periodos = True


# ---------------------------------------------------------------------------
# Lectura de periodos y periodo inicial
# ---------------------------------------------------------------------------

def _leer_periodos(conn: Connection) -> list:
    return list(conn.execute(select(_TABLA_PERIODOS).order_by(_TABLA_PERIODOS.c.anio)).mappings())


def _anio_actual() -> int:
    from app.services.prestamos_service import hoy_colombia
    return hoy_colombia().year


def asegurar_periodo_inicial(conn: Connection) -> None:
    """Registra los datos existentes como el año en curso (2026), sin moverlos."""
    if conn.execute(select(func.count()).select_from(_TABLA_PERIODOS)).scalar_one():
        return
    conn.execute(insert(_TABLA_PERIODOS).values(
        anio=_anio_actual(), esquema=None, activo=True, socios_copiados=0,
    ))


def leer_periodos(engine: Engine) -> list:
    _preparar_sqlite(engine)
    try:
        with engine.connect() as conn:
            periodos = _leer_periodos(conn)
    except (ProgrammingError, OperationalError):
        # Base aún sin migrar (falta "python manage_db.py upgrade"): se sigue
        # trabajando con los datos de siempre como único año, sin escribir nada.
        return [{"id": 0, "anio": _anio_actual(), "esquema": None, "activo": True,
                 "copiado_de_anio": None, "socios_copiados": 0, "usuario_nombre": None, "created_at": None}]
    if periodos:
        return periodos
    try:
        with engine.begin() as conn:
            asegurar_periodo_inicial(conn)
    except IntegrityError:
        pass  # Otra petición lo creó al mismo tiempo.
    with engine.connect() as conn:
        return _leer_periodos(conn)


def _activo(periodos: list):
    return next((p for p in periodos if p["activo"]), periodos[-1])


# ---------------------------------------------------------------------------
# Sesión por petición
# ---------------------------------------------------------------------------

def configurar_periodo(db: Session, cabecera: Optional[str]) -> None:
    """Liga la sesión al año activo o al indicado en la cabecera X-Periodo."""
    base = db.info.get("motor_base") or db.get_bind()
    periodos = leer_periodos(base)
    activo = _activo(periodos)
    elegido = activo
    if cabecera and cabecera.strip():
        try:
            anio = int(cabecera.strip())
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Año consultado inválido")
        elegido = next((p for p in periodos if p["anio"] == anio), None)
        if elegido is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"El año {anio} no existe")
    db.info.update(
        motor_base=base,
        periodo_id=elegido["id"],
        periodo_anio=elegido["anio"],
        periodo_activo_anio=activo["anio"],
        solo_lectura=elegido["id"] != activo["id"],
    )
    db.bind = motor_periodo(base, elegido["esquema"])


def anio_del_periodo(db: Session) -> int:
    """Año del periodo con el que trabaja la sesión (el activo por defecto)."""
    return db.info.get("periodo_anio") or _anio_actual()


# ---------------------------------------------------------------------------
# Protección de años de solo consulta
# ---------------------------------------------------------------------------

def _es_de_periodo(mapper) -> bool:
    return mapper is None or mapper.local_table.schema != SCHEMA_COMUN


@event.listens_for(Session, "before_flush")
def _bloquear_cambios(session: Session, _flush_context, _instances) -> None:
    if not session.info.get("solo_lectura"):
        return
    cambios = [*session.new, *session.deleted, *(o for o in session.dirty if session.is_modified(o))]
    if any(_es_de_periodo(sa_inspect(obj).mapper) for obj in cambios):
        raise PeriodoSoloLectura(session.info.get("periodo_anio"))


@event.listens_for(Session, "do_orm_execute")
def _bloquear_sentencias(state) -> None:
    if not state.session.info.get("solo_lectura"):
        return
    if (state.is_insert or state.is_update or state.is_delete) and _es_de_periodo(state.bind_mapper):
        raise PeriodoSoloLectura(state.session.info.get("periodo_anio"))


# ---------------------------------------------------------------------------
# Resumen y creación de años
# ---------------------------------------------------------------------------

def resumen_periodo(engine: Engine, periodo) -> dict[str, Any]:
    from app.models.finanzas import FinanzaSocio
    from app.models.prestamo import Prestamo
    from app.models.socio import Socio
    from app.models.gastos import GastoGeneral

    s, f, p, g = Socio.__table__, FinanzaSocio.__table__, Prestamo.__table__, GastoGeneral.__table__
    cero = 0
    with motor_periodo(engine, periodo["esquema"]).connect() as conn:
        socios, socios_activos = conn.execute(select(
            func.count(s.c.id), func.coalesce(func.sum(case((s.c.is_active.is_(True), 1), else_=0)), 0)
        )).one()
        ahorro = conn.execute(select(func.coalesce(func.sum(case(
            (f.c.tipo_movimiento == "APORTE", f.c.monto),
            (f.c.tipo_movimiento == "RETIRO_AHORRO", -f.c.monto),
            else_=cero,
        )), cero))).scalar_one()
        prestamos, prestado = conn.execute(select(
            func.count(p.c.id), func.coalesce(func.sum(p.c.monto_prestado), cero)
        )).one()
        gastos = conn.execute(select(func.coalesce(func.sum(g.c.monto), cero))).scalar_one()
    return {
        "socios": socios,
        "socios_activos": int(socios_activos or 0),
        "total_ahorro": ahorro,
        "prestamos": prestamos,
        "total_prestado": prestado,
        "total_gastos": gastos,
    }


def crear_nuevo_periodo(base: Engine, anio_confirmado: int, usuario_nombre: Optional[str]) -> dict:
    """Crea el año siguiente al último, vacío salvo por los socios del año activo.

    Todo ocurre en una sola transacción: si algo falla, no queda nada a medias.
    Los datos de los años anteriores no se tocan.
    """
    from app.models.historial import HistorialMovimiento
    from app.models.socio import Socio

    _preparar_sqlite(base)
    es_postgres = base.dialect.name == "postgresql"
    mapa_comun = mapa_esquemas(base, None)

    with base.connect() as conn:
        conn.execution_options(schema_translate_map=mapa_comun)
        if es_postgres:
            # Serializa creaciones simultáneas (doble clic, dos pestañas...).
            conn.execute(text("SELECT pg_advisory_xact_lock(82146322)"))
        periodos = _leer_periodos(conn)
        if not periodos:
            asegurar_periodo_inicial(conn)
            periodos = _leer_periodos(conn)
        origen = _activo(periodos)
        nuevo_anio = max(p["anio"] for p in periodos) + 1
        if anio_confirmado != nuevo_anio:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"El año {anio_confirmado} ya existe o no es el siguiente. El próximo año a crear es {nuevo_anio}.",
            )
        esquema = nombre_esquema(base, nuevo_anio)
        if any(p["esquema"] == esquema for p in periodos):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"El año {nuevo_anio} ya existe")

        # 1. Socios del último año (el activo), con sus datos personales e ID.
        socios = [dict(fila) for fila in conn.execute(
            select(Socio.__table__).order_by(Socio.__table__.c.id),
            execution_options={"schema_translate_map": mapa_esquemas(base, origen["esquema"])},
        ).mappings()]

        # 2. Esquema y tablas vacías del año nuevo.
        if es_postgres:
            conn.execute(text(f'CREATE SCHEMA "{esquema}"'))
        else:
            _adjuntar_sqlite(conn.connection.dbapi_connection, [esquema])
        mapa_nuevo = mapa_esquemas(base, esquema)
        conn.execution_options(schema_translate_map=mapa_nuevo)
        Base.metadata.create_all(conn, tables=tablas_de_periodo())
        if conn.execute(select(func.count()).select_from(Socio.__table__)).scalar_one():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"El año {nuevo_anio} ya tiene socios registrados")

        # 3. Copia de socios: mismos datos, sin movimientos financieros.
        if socios:
            conn.execute(insert(Socio.__table__), socios)
        if es_postgres:
            conn.execute(text(
                f"SELECT setval(pg_get_serial_sequence('\"{esquema}\".socios', 'id'), "
                f"(SELECT COALESCE(MAX(id), 0) + 1 FROM \"{esquema}\".socios), false)"
            ))
        conn.execute(insert(HistorialMovimiento.__table__).values(
            modulo="Años",
            tipo_accion="CREAR",
            descripcion=(
                f"Inicio del año {nuevo_anio}: se copiaron {len(socios)} socios del año {origen['anio']}. "
                "Ahorros, préstamos, abonos, intereses, gastos, contabilidad y liquidación inician en cero."
            ),
            entidad_tipo="Periodo",
            usuario_nombre=usuario_nombre,
            revertido=False,
        ))

        # 4. El año nuevo pasa a ser el activo; los anteriores quedan de consulta.
        conn.execution_options(schema_translate_map=mapa_comun)
        conn.execute(update(_TABLA_PERIODOS).where(_TABLA_PERIODOS.c.activo.is_(True)).values(activo=False))
        conn.execute(insert(_TABLA_PERIODOS).values(
            anio=nuevo_anio, esquema=esquema, activo=True, copiado_de_anio=origen["anio"],
            socios_copiados=len(socios), usuario_nombre=usuario_nombre,
        ))
        conn.commit()

    return {"anio": nuevo_anio, "copiado_de_anio": origen["anio"], "socios_copiados": len(socios)}
