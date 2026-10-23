"""Saldo y estado de un préstamo derivados de sus abonos persistidos."""
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models.prestamo import Prestamo, AbonoPrestamo, EstadoPrestamo


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
    elif prestamo.estado != EstadoPrestamo.EN_MORA.value:
        prestamo.estado = EstadoPrestamo.PENDIENTE.value
