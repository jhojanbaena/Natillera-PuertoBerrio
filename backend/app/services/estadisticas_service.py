"""Estadísticas de los movimientos económicos de la natillera.

Solo lee la base de datos: no modifica registros ni cálculos financieros. Toma
los movimientos tal como están registrados en cada módulo del año consultado:

- Socios: aportes, pagos de multas, retiros de ahorro y multas impuestas.
- Préstamos: préstamos entregados, abonos a capital e intereses cobrados.
- Eventos: ingresos e inversión de cada evento, ventas e inversión de cada
  rifa y ganancias de cada reunión.
- Actividades de los socios y gastos generales.

Las fechas se toman en hora de Colombia, igual que en el resto del sistema.

Cada movimiento lleva su concepto (tipo del catálogo), el módulo de origen y una
descripción legible (socio, préstamo, cuota, evento...) tomada del registro real,
para que las tablas muestren de dónde proviene cada peso.
"""
from __future__ import annotations

import html
import re

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Callable, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.periodos import anio_del_periodo
from app.models.actividad import Actividad
from app.models.actividad_socio import ActividadSocio
from app.models.finanzas import FinanzaSocio, TipoMovimientoFinanciero
from app.models.gastos import GastoGeneral
from app.models.prestamo import AbonoPrestamo, Prestamo
from app.models.reunion import Reunion
from app.models.rifa import Rifa
from app.models.socio import Socio
from app.services.prestamos_service import ZONA_COLOMBIA

INGRESO, EGRESO, OTRO = "INGRESO", "EGRESO", "OTRO"

# Catálogo de tipos de movimiento: clave -> (etiqueta, naturaleza).
# OTRO: registros económicos que no son entrada ni salida de dinero (una multa
# impuesta es una deuda del socio; el dinero entra cuando la paga).
TIPOS_MOVIMIENTO: dict[str, tuple[str, str]] = {
    "APORTE": ("Aportes de ahorro", INGRESO),
    "PAGO_MULTA": ("Pagos de multas", INGRESO),
    "ABONO_CAPITAL": ("Abonos a capital de préstamos", INGRESO),
    "INTERES_PRESTAMO": ("Intereses de préstamos", INGRESO),
    "INGRESO_EVENTO": ("Ingresos de eventos", INGRESO),
    "INGRESO_RIFA": ("Ventas de rifas", INGRESO),
    "INGRESO_REUNION": ("Ganancias de reuniones", INGRESO),
    "GANANCIA_ACTIVIDAD_SOCIO": ("Ganancias de actividades de socios", INGRESO),
    "RETIRO_AHORRO": ("Retiros de ahorro", EGRESO),
    "DESEMBOLSO_PRESTAMO": ("Préstamos entregados", EGRESO),
    "INVERSION_EVENTO": ("Inversión en eventos", EGRESO),
    "INVERSION_RIFA": ("Inversión en premios de rifas", EGRESO),
    "GASTO_GENERAL": ("Gastos generales", EGRESO),
    "MULTA": ("Multas impuestas", OTRO),
}

# Tipos ligados a un evento (actividad, rifa o reunión).
# Módulo del sistema del que proviene cada tipo de movimiento.
ORIGEN_TIPO: dict[str, str] = {
    "APORTE": "Socios", "PAGO_MULTA": "Socios", "RETIRO_AHORRO": "Socios", "MULTA": "Socios",
    "ABONO_CAPITAL": "Préstamos", "INTERES_PRESTAMO": "Préstamos", "DESEMBOLSO_PRESTAMO": "Préstamos",
    "INGRESO_EVENTO": "Eventos", "INVERSION_EVENTO": "Eventos",
    "INGRESO_RIFA": "Rifas", "INVERSION_RIFA": "Rifas",
    "INGRESO_REUNION": "Reuniones",
    "GANANCIA_ACTIVIDAD_SOCIO": "Actividades de socios",
    "GASTO_GENERAL": "Gastos generales",
}

TIPOS_DE_EVENTO = {
    "actividad": ("INGRESO_EVENTO", "INVERSION_EVENTO"),
    "rifa": ("INGRESO_RIFA", "INVERSION_RIFA"),
    "reunion": ("INGRESO_REUNION",),
}

MAX_DIAS_SERIE_DIARIA = 62


@dataclass
class Movimiento:
    tipo: str
    fecha: date
    monto: Decimal
    evento: Optional[str] = None
    evento_nombre: Optional[str] = None
    descripcion: str = ""
    # Registro de origen, p. ej. "finanza-12", "abono-7": evita contar dos veces.
    referencia: str = ""


MESES_TEXTO = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _texto(valor) -> str:
    """Texto plano (las descripciones pueden venir con formato HTML)."""
    limpio = re.sub(r"<[^>]+>", " ", html.unescape(str(valor or "")))
    return re.sub(r"\s+", " ", limpio).strip()


def _nombres_socios(db) -> dict[int, str]:
    return dict(db.execute(select(Socio.id, Socio.nombre)).all())


def _socio(nombres: dict[int, str], socio_id) -> str:
    return nombres.get(socio_id) or f"Socio #{socio_id}"


def _fecha_colombia(valor) -> date:
    """Fecha (día) en Colombia de un valor de fecha u hora guardado en la base."""
    if isinstance(valor, datetime):
        if valor.tzinfo is None:  # SQLite guarda las horas en UTC sin zona.
            valor = valor.replace(tzinfo=timezone.utc)
        return valor.astimezone(ZONA_COLOMBIA).date()
    return valor


def _limites_utc(desde: Optional[date], hasta: Optional[date]) -> tuple[Optional[datetime], Optional[datetime]]:
    """Rango de días en Colombia expresado en UTC (fin exclusivo)."""
    inicio = datetime.combine(desde, time.min, ZONA_COLOMBIA).astimezone(timezone.utc) if desde else None
    fin = (datetime.combine(hasta + timedelta(days=1), time.min, ZONA_COLOMBIA).astimezone(timezone.utc)
           if hasta else None)
    return inicio, fin


def _condiciones(columna, desde: Optional[date], hasta: Optional[date], es_fecha_hora: bool) -> list:
    if es_fecha_hora:
        desde, hasta_excl = _limites_utc(desde, hasta)
        condiciones = []
        if desde:
            condiciones.append(columna >= desde)
        if hasta_excl:
            condiciones.append(columna < hasta_excl)
        return condiciones
    condiciones = []
    if desde:
        condiciones.append(columna >= desde)
    if hasta:
        condiciones.append(columna <= hasta)
    return condiciones


# ---------------------------------------------------------------------------
# Lectura de movimientos por origen
# ---------------------------------------------------------------------------

ETIQUETA_FINANZA = {
    "APORTE": "Aporte de ahorro", "PAGO_MULTA": "Pago de multa",
    "RETIRO_AHORRO": "Retiro de ahorro", "MULTA": "Multa impuesta",
}


def _finanzas(db, tipo_db: str, tipo: str, desde, hasta) -> Iterable[Movimiento]:
    nombres = _nombres_socios(db)
    filas = db.execute(
        select(FinanzaSocio.id, FinanzaSocio.socio_id, FinanzaSocio.fecha, FinanzaSocio.monto,
               FinanzaSocio.descripcion, FinanzaSocio.periodo)
        .where(FinanzaSocio.tipo_movimiento == tipo_db, *_condiciones(FinanzaSocio.fecha, desde, hasta, True))
    ).all()
    movimientos = []
    for i, socio_id, fecha, monto, descripcion, periodo in filas:
        partes = [f"{ETIQUETA_FINANZA[tipo_db]} de {_socio(nombres, socio_id)}"]
        if periodo:
            try:
                partes.append(f"mes de {MESES_TEXTO[int(periodo[5:7]) - 1]} {periodo[:4]}")
            except (ValueError, IndexError):
                partes.append(periodo)
        detalle = _texto(descripcion)
        if detalle and not (tipo_db == "APORTE" and periodo and detalle.lower().startswith("aporte mensual")):
            partes.append(detalle)
        movimientos.append(Movimiento(tipo, _fecha_colombia(fecha), monto, descripcion=" · ".join(partes),
                                      referencia=f"finanza-{i}"))
    return movimientos


def _abonos(db, columna, tipo: str, desde, hasta) -> Iterable[Movimiento]:
    nombres = _nombres_socios(db)
    filas = db.execute(
        select(AbonoPrestamo.id, AbonoPrestamo.prestamo_id, AbonoPrestamo.numero_cuota, Prestamo.socio_id,
               AbonoPrestamo.fecha_pago, columna)
        .join(Prestamo, Prestamo.id == AbonoPrestamo.prestamo_id)
        .where(*_condiciones(AbonoPrestamo.fecha_pago, desde, hasta, True))
    ).all()
    concepto = "Abono a capital" if tipo == "ABONO_CAPITAL" else "Interés cobrado"
    return [
        Movimiento(tipo, _fecha_colombia(f), m,
                   descripcion=f"{concepto} del préstamo #{prestamo_id} de {_socio(nombres, socio_id)} · cuota #{cuota}",
                   referencia=f"abono-{i}")
        for i, prestamo_id, cuota, socio_id, f, m in filas
    ]


def _desembolsos(db, desde, hasta) -> Iterable[Movimiento]:
    nombres = _nombres_socios(db)
    filas = db.execute(
        select(Prestamo.id, Prestamo.socio_id, Prestamo.fecha_prestamo, Prestamo.monto_prestado, Prestamo.numero_cuotas)
        .where(*_condiciones(Prestamo.fecha_prestamo, desde, hasta, False))
    ).all()
    return [
        Movimiento("DESEMBOLSO_PRESTAMO", f, m,
                   descripcion=f"Préstamo #{i} entregado a {_socio(nombres, socio_id)} · {cuotas} cuotas",
                   referencia=f"prestamo-{i}")
        for i, socio_id, f, m, cuotas in filas
    ]


def _gastos(db, desde, hasta) -> Iterable[Movimiento]:
    filas = db.execute(
        select(GastoGeneral.id, GastoGeneral.created_at, GastoGeneral.monto, GastoGeneral.descripcion)
        .where(*_condiciones(GastoGeneral.created_at, desde, hasta, True))
    ).all()
    return [
        Movimiento("GASTO_GENERAL", _fecha_colombia(f), m,
                   descripcion=f"Gasto general: {_texto(descripcion) or 'sin descripción'}", referencia=f"gasto-{i}")
        for i, f, m, descripcion in filas
    ]


def _actividades_socio(db, desde, hasta) -> Iterable[Movimiento]:
    nombres = _nombres_socios(db)
    filas = db.execute(
        select(ActividadSocio.id, ActividadSocio.socio_id, ActividadSocio.tipo, ActividadSocio.nombre,
               ActividadSocio.mes, ActividadSocio.cantidad_vendida, ActividadSocio.valor_unidad,
               ActividadSocio.created_at, ActividadSocio.ganancia)
        .where(*_condiciones(ActividadSocio.created_at, desde, hasta, True))
    ).all()
    movimientos = []
    for i, socio_id, tipo, nombre, mes, cantidad, valor_unidad, f, m in filas:
        if tipo == "RIFA_INTERNA":
            texto = "Rifa interna" + (f" de {MESES_TEXTO[mes - 1]}" if mes and 1 <= mes <= 12 else "")
        else:
            texto = f"Actividad '{nombre}'"
        texto += f" de {_socio(nombres, socio_id)}"
        if cantidad is not None:
            texto += f" · {cantidad} vendidas"
            if valor_unidad is not None:
                texto += f" a ${valor_unidad:,.0f} c/u".replace(",", ".")
        movimientos.append(Movimiento("GANANCIA_ACTIVIDAD_SOCIO", _fecha_colombia(f), m, descripcion=texto,
                                      referencia=f"actividad_socio-{i}"))
    return movimientos


def _eventos(db, tipos: set[str], desde, hasta, evento: Optional[str]) -> list[Movimiento]:
    """Movimientos de actividades, rifas y reuniones (opcionalmente de un solo evento)."""
    clase_evento, id_evento = (evento.split("-", 1) if evento else (None, None))
    movimientos: list[Movimiento] = []

    if clase_evento in (None, "actividad") and tipos & {"INGRESO_EVENTO", "INVERSION_EVENTO"}:
        q = select(Actividad.id, Actividad.nombre, Actividad.fecha, Actividad.ingresos_brutos, Actividad.inversion) \
            .where(*_condiciones(Actividad.fecha, desde, hasta, False))
        if id_evento:
            q = q.where(Actividad.id == int(id_evento))
        for i, nombre, fecha, ingresos, inversion in db.execute(q).all():
            clave = f"actividad-{i}"
            if "INGRESO_EVENTO" in tipos:
                movimientos.append(Movimiento("INGRESO_EVENTO", fecha, ingresos or Decimal("0"), clave, nombre,
                                              f"Ingresos brutos del evento '{nombre}'", f"{clave}-ingreso"))
            if "INVERSION_EVENTO" in tipos:
                movimientos.append(Movimiento("INVERSION_EVENTO", fecha, inversion or Decimal("0"), clave, nombre,
                                              f"Inversión en el evento '{nombre}'", f"{clave}-inversion"))

    if clase_evento in (None, "rifa") and tipos & {"INGRESO_RIFA", "INVERSION_RIFA"}:
        q = select(Rifa.id, Rifa.nombre, Rifa.fecha, Rifa.boletas_vendidas, Rifa.valor_boleta, Rifa.inversion_premios) \
            .where(*_condiciones(Rifa.fecha, desde, hasta, False))
        if id_evento:
            q = q.where(Rifa.id == int(id_evento))
        for i, nombre, fecha, vendidas, valor, inversion in db.execute(q).all():
            clave = f"rifa-{i}"
            if "INGRESO_RIFA" in tipos:
                # Mismo recaudo bruto que usa el módulo de rifas: boletas vendidas x valor.
                recaudo = Decimal(vendidas or 0) * (valor or Decimal("0"))
                valor_txt = f"${(valor or Decimal('0')):,.0f}".replace(",", ".")
                movimientos.append(Movimiento("INGRESO_RIFA", fecha, recaudo, clave, f"Rifa: {nombre}",
                                              f"Venta de la rifa '{nombre}' · {vendidas or 0} boletas a {valor_txt}",
                                              f"{clave}-ingreso"))
            if "INVERSION_RIFA" in tipos:
                movimientos.append(Movimiento("INVERSION_RIFA", fecha, inversion or Decimal("0"), clave, f"Rifa: {nombre}",
                                              f"Premios de la rifa '{nombre}'", f"{clave}-inversion"))

    if clase_evento in (None, "reunion") and "INGRESO_REUNION" in tipos:
        q = select(Reunion.id, Reunion.tema, Reunion.fecha, Reunion.ganancias_reunion) \
            .where(*_condiciones(Reunion.fecha, desde, hasta, False))
        if id_evento:
            q = q.where(Reunion.id == int(id_evento))
        for i, tema, fecha, ganancia in db.execute(q).all():
            movimientos.append(Movimiento("INGRESO_REUNION", fecha, ganancia or Decimal("0"), f"reunion-{i}", f"Reunión: {tema}",
                                          f"Ganancias de la reunión '{_texto(tema)}'", f"reunion-{i}-ingreso"))

    return movimientos


_ORIGENES_SIN_EVENTO: dict[str, Callable] = {
    "APORTE": lambda db, d, h: _finanzas(db, TipoMovimientoFinanciero.APORTE.value, "APORTE", d, h),
    "PAGO_MULTA": lambda db, d, h: _finanzas(db, TipoMovimientoFinanciero.PAGO_MULTA.value, "PAGO_MULTA", d, h),
    "RETIRO_AHORRO": lambda db, d, h: _finanzas(db, TipoMovimientoFinanciero.RETIRO_AHORRO.value, "RETIRO_AHORRO", d, h),
    "MULTA": lambda db, d, h: _finanzas(db, TipoMovimientoFinanciero.MULTA.value, "MULTA", d, h),
    "ABONO_CAPITAL": lambda db, d, h: _abonos(db, AbonoPrestamo.monto_capital, "ABONO_CAPITAL", d, h),
    "INTERES_PRESTAMO": lambda db, d, h: _abonos(db, AbonoPrestamo.monto_interes, "INTERES_PRESTAMO", d, h),
    "DESEMBOLSO_PRESTAMO": _desembolsos,
    "GASTO_GENERAL": _gastos,
    "GANANCIA_ACTIVIDAD_SOCIO": _actividades_socio,
}


def leer_movimientos(db: Session, filtros: dict) -> list[Movimiento]:
    desde, hasta = filtros.get("fecha_desde"), filtros.get("fecha_hasta")
    evento = filtros.get("evento")
    tipos = set(filtros.get("tipos") or TIPOS_MOVIMIENTO)
    if evento:
        # Un evento solo tiene sus propios movimientos (ingresos e inversión).
        tipos &= set(TIPOS_DE_EVENTO[evento.split("-", 1)[0]])
    movimientos: list[Movimiento] = []
    if not evento:
        for tipo, origen in _ORIGENES_SIN_EVENTO.items():
            if tipo in tipos:
                movimientos.extend(origen(db, desde, hasta))
    movimientos.extend(_eventos(db, tipos, desde, hasta, evento))
    return [m for m in movimientos if m.monto]


# ---------------------------------------------------------------------------
# Agregación
# ---------------------------------------------------------------------------

def _num(valor: Decimal) -> float:
    return float(Decimal(valor).quantize(Decimal("0.01")))


def _claves_serie(desde: date, hasta: date, diaria: bool) -> list[str]:
    claves = []
    if diaria:
        dia = desde
        while dia <= hasta:
            claves.append(dia.isoformat())
            dia += timedelta(days=1)
        return claves
    anio, mes = desde.year, desde.month
    while (anio, mes) <= (hasta.year, hasta.month):
        claves.append(f"{anio:04d}-{mes:02d}")
        anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    return claves


def calcular_estadistica(db: Session, filtros: dict) -> dict:
    """Resultados listos para graficar y para guardar como fotografía (JSON)."""
    movimientos = leer_movimientos(db, filtros)
    desde, hasta = filtros.get("fecha_desde"), filtros.get("fecha_hasta")
    if movimientos:
        desde = desde or min(m.fecha for m in movimientos)
        hasta = hasta or max(m.fecha for m in movimientos)

    totales = {INGRESO: Decimal("0"), EGRESO: Decimal("0"), OTRO: Decimal("0")}
    por_tipo: dict[str, list] = defaultdict(lambda: [Decimal("0"), 0])
    por_evento: dict[str, dict] = {}
    for m in movimientos:
        naturaleza = TIPOS_MOVIMIENTO[m.tipo][1]
        totales[naturaleza] += m.monto
        por_tipo[m.tipo][0] += m.monto
        por_tipo[m.tipo][1] += 1
        if m.evento:
            ev = por_evento.setdefault(m.evento, {"evento": m.evento, "nombre": m.evento_nombre, "fecha": m.fecha,
                                                  "origen": ORIGEN_TIPO.get(m.tipo, ""),
                                                  INGRESO: Decimal("0"), EGRESO: Decimal("0")})
            ev[naturaleza] += m.monto

    serie, granularidad = [], None
    diaria = False
    if desde and hasta:
        diaria = (hasta - desde).days < MAX_DIAS_SERIE_DIARIA
        granularidad = "dia" if diaria else "mes"
        cubetas = {c: {INGRESO: Decimal("0"), EGRESO: Decimal("0"), OTRO: Decimal("0")}
                   for c in _claves_serie(desde, hasta, diaria)}
        # Conceptos de cada periodo: total y cantidad por tipo de movimiento.
        conceptos: dict[str, dict[str, list]] = {c: {} for c in cubetas}
        for m in movimientos:
            clave = m.fecha.isoformat() if diaria else m.fecha.strftime("%Y-%m")
            if clave in cubetas:
                cubetas[clave][TIPOS_MOVIMIENTO[m.tipo][1]] += m.monto
                acumulado = conceptos[clave].setdefault(m.tipo, [Decimal("0"), 0])
                acumulado[0] += m.monto
                acumulado[1] += 1
        serie = [{
            "periodo": clave,
            "ingresos": _num(v[INGRESO]),
            "egresos": _num(v[EGRESO]),
            "otros": _num(v[OTRO]),
            "balance": _num(v[INGRESO] - v[EGRESO]),
            "por_tipo": sorted([{
                "tipo": tipo,
                "etiqueta": TIPOS_MOVIMIENTO[tipo][0],
                "naturaleza": TIPOS_MOVIMIENTO[tipo][1],
                "total": _num(total),
                "cantidad": cantidad,
            } for tipo, (total, cantidad) in conceptos[clave].items()], key=lambda x: -x["total"]),
        } for clave, v in cubetas.items()]

    # Detalle: cada registro con su concepto, origen y descripción (sin duplicados).
    vistos: set[tuple[str, str]] = set()
    detalle = []
    for m in sorted(movimientos, key=lambda x: (x.fecha, x.tipo, x.referencia)):
        llave = (m.tipo, m.referencia)
        if m.referencia and llave in vistos:
            continue
        vistos.add(llave)
        detalle.append({
            "fecha": m.fecha.isoformat(),
            "periodo": m.fecha.isoformat() if diaria else m.fecha.strftime("%Y-%m"),
            "tipo": m.tipo,
            "concepto": TIPOS_MOVIMIENTO[m.tipo][0],
            "naturaleza": TIPOS_MOVIMIENTO[m.tipo][1],
            "origen": ORIGEN_TIPO.get(m.tipo, ""),
            "descripcion": m.descripcion or TIPOS_MOVIMIENTO[m.tipo][0],
            "referencia": m.referencia,
            "monto": _num(m.monto),
        })

    return {
        "anio": anio_del_periodo(db),
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "rango": {"desde": desde.isoformat() if desde else None, "hasta": hasta.isoformat() if hasta else None},
        "granularidad": granularidad,
        "totales": {
            "ingresos": _num(totales[INGRESO]),
            "egresos": _num(totales[EGRESO]),
            "otros": _num(totales[OTRO]),
            "balance": _num(totales[INGRESO] - totales[EGRESO]),
            "cantidad": len(movimientos),
        },
        "por_tipo": sorted([{
            "tipo": tipo,
            "etiqueta": TIPOS_MOVIMIENTO[tipo][0],
            "naturaleza": TIPOS_MOVIMIENTO[tipo][1],
            "origen": ORIGEN_TIPO.get(tipo, ""),
            "total": _num(total),
            "cantidad": cantidad,
        } for tipo, (total, cantidad) in por_tipo.items()], key=lambda x: -x["total"]),
        "serie": serie,
        "movimientos": detalle,
        "por_evento": sorted([{
            "evento": ev["evento"],
            "nombre": ev["nombre"],
            "origen": ev["origen"],
            "fecha": ev["fecha"].isoformat(),
            "ingresos": _num(ev[INGRESO]),
            "egresos": _num(ev[EGRESO]),
            "balance": _num(ev[INGRESO] - ev[EGRESO]),
        } for ev in por_evento.values()], key=lambda x: x["fecha"]),
    }


def listar_eventos(db: Session) -> list[dict]:
    """Eventos del año consultado que tienen movimientos económicos."""
    eventos = []
    for i, nombre, fecha in db.execute(select(Actividad.id, Actividad.nombre, Actividad.fecha)).all():
        eventos.append({"clave": f"actividad-{i}", "nombre": nombre, "categoria": "Evento", "fecha": fecha.isoformat()})
    for i, nombre, fecha in db.execute(select(Rifa.id, Rifa.nombre, Rifa.fecha)).all():
        eventos.append({"clave": f"rifa-{i}", "nombre": nombre, "categoria": "Rifa", "fecha": fecha.isoformat()})
    for i, tema, fecha in db.execute(select(Reunion.id, Reunion.tema, Reunion.fecha)).all():
        eventos.append({"clave": f"reunion-{i}", "nombre": tema, "categoria": "Reunión", "fecha": fecha.isoformat()})
    return sorted(eventos, key=lambda e: (e["fecha"], e["nombre"]), reverse=True)
