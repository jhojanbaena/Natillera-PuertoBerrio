"""Saldo, estado y mora de un préstamo derivados de sus abonos persistidos.

Regla de mora: se espera una cuota mensual a partir de la fecha del préstamo.
La cuota N vence N meses después del desembolso; si pasan más de
DIAS_GRACIA_MORA días desde ese vencimiento y el número de cuotas pagadas es
menor que el de cuotas vencidas, el préstamo queda EN_MORA. También entra en
mora si supera la fecha de vencimiento (más la gracia) con deuda pendiente.
El estado se recalcula siempre: al ponerse al día vuelve a PENDIENTE.
"""
import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models.prestamo import Prestamo, AbonoPrestamo, EstadoPrestamo

DIAS_GRACIA_MORA = 5
ZONA_COLOMBIA = timezone(timedelta(hours=-5))


def hoy_colombia() -> date:
    """Fecha actual en Colombia (los servidores serverless corren en UTC)."""
    return datetime.now(ZONA_COLOMBIA).date()


def fecha_a_datetime(fecha: date) -> datetime:
    """Fecha elegida por el usuario -> mediodía de Colombia en UTC.

    El mediodía evita que el registro cambie de día (o de año) por la zona horaria.
    """
    return datetime(fecha.year, fecha.month, fecha.day, 12, tzinfo=ZONA_COLOMBIA).astimezone(timezone.utc)


def validar_fecha_registro(fecha: Optional[date], minima: Optional[date] = None) -> None:
    from fastapi import HTTPException  # evitar dependencia web al importar modelos

    if fecha is None:
        return
    if fecha > hoy_colombia():
        raise HTTPException(status_code=422, detail="La fecha no puede ser futura")
    if minima and fecha < minima:
        raise HTTPException(status_code=422, detail="La fecha del abono no puede ser anterior a la del préstamo")


def sumar_meses(fecha: date, meses: int) -> date:
    """Suma meses calendario conservando el día o usando el último del mes."""
    total = fecha.month - 1 + meses
    anio, mes = fecha.year + total // 12, total % 12 + 1
    return date(anio, mes, min(fecha.day, calendar.monthrange(anio, mes)[1]))


def fecha_cuota(prestamo: Prestamo, numero: int) -> date:
    return sumar_meses(prestamo.fecha_prestamo, numero)


def cuotas_vencidas(prestamo: Prestamo, hoy: Optional[date] = None) -> int:
    """Cuotas cuyo vencimiento más los días de gracia ya pasó."""
    hoy = hoy or hoy_colombia()
    limite = hoy - timedelta(days=DIAS_GRACIA_MORA)
    vencidas = 0
    while vencidas < prestamo.numero_cuotas and fecha_cuota(prestamo, vencidas + 1) < limite:
        vencidas += 1
    return vencidas


def cuotas_atrasadas(prestamo: Prestamo, hoy: Optional[date] = None) -> int:
    if prestamo.estado == EstadoPrestamo.PAGADO.value:
        return 0
    return max(0, cuotas_vencidas(prestamo, hoy) - prestamo.cuotas_pagadas)


def fecha_proxima_cuota(prestamo: Prestamo) -> Optional[date]:
    if prestamo.estado == EstadoPrestamo.PAGADO.value:
        return None
    if prestamo.cuotas_pagadas < prestamo.numero_cuotas:
        return fecha_cuota(prestamo, prestamo.cuotas_pagadas + 1)
    return prestamo.fecha_vencimiento


def esta_en_mora(prestamo: Prestamo, hoy: Optional[date] = None) -> bool:
    hoy = hoy or hoy_colombia()
    if cuotas_atrasadas(prestamo, hoy) > 0:
        return True
    gracia = timedelta(days=DIAS_GRACIA_MORA)
    return bool(prestamo.fecha_vencimiento and hoy - gracia > prestamo.fecha_vencimiento)


def _estado_sin_pago(prestamo: Prestamo, hoy: Optional[date] = None) -> str:
    return EstadoPrestamo.EN_MORA.value if esta_en_mora(prestamo, hoy) else EstadoPrestamo.PENDIENTE.value


def recalcular_prestamo(db: Session, prestamo: Prestamo) -> None:
    # autoflush está deshabilitado: incluir altas, ediciones y bajas pendientes.
    db.flush()
    capital, intereses, cuotas = db.execute(select(
        func.coalesce(func.sum(AbonoPrestamo.monto_capital), Decimal("0.00")),
        func.coalesce(func.sum(AbonoPrestamo.monto_interes), Decimal("0.00")),
        func.count(AbonoPrestamo.id),
    ).where(AbonoPrestamo.prestamo_id == prestamo.id)).one()
    prestamo.saldo_pendiente = max(Decimal("0.00"), prestamo.monto_prestado - capital)
    prestamo.cuotas_pagadas = cuotas
    if prestamo.saldo_pendiente == 0 and intereses >= prestamo.total_intereses:
        prestamo.estado = EstadoPrestamo.PAGADO.value
    else:
        # Primero se deja como no pagado para que el cálculo de atraso aplique.
        prestamo.estado = EstadoPrestamo.PENDIENTE.value
        prestamo.estado = _estado_sin_pago(prestamo)


def sincronizar_moras(db: Session, hoy: Optional[date] = None) -> int:
    """Actualiza PENDIENTE/EN_MORA de los préstamos no pagados según la fecha.

    La mora depende del paso del tiempo, no solo de los abonos, por eso se
    sincroniza antes de leer préstamos. Devuelve cuántos cambiaron de estado.
    """
    prestamos = db.execute(
        select(Prestamo).where(Prestamo.estado != EstadoPrestamo.PAGADO.value)
    ).scalars().all()
    cambios = 0
    for prestamo in prestamos:
        nuevo = _estado_sin_pago(prestamo, hoy)
        if prestamo.estado != nuevo:
            prestamo.estado = nuevo
            cambios += 1
    if cambios:
        db.commit()
    return cambios
