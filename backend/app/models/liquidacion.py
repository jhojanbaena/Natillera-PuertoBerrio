"""Modelos ORM para el control de pagos de la Liquidación anual.

- LiquidacionFondo: dinero general destinado a liquidar un año (una fila por año).
  Su fila se bloquea (SELECT ... FOR UPDATE) para serializar los pagos del año.
- LiquidacionPago: registro de que a un socio se le pagó su liquidación de un año.
  La restricción única (anio, socio_id) impide liquidar dos veces al mismo socio.

El saldo disponible nunca se guarda: siempre es monto_general - suma(pagos),
así revertir un pago (borrarlo) restaura el saldo sin riesgo de descuadres.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class MetodoPagoLiquidacion:
    EFECTIVO = "EFECTIVO"
    TRANSFERENCIA = "TRANSFERENCIA"


class LiquidacionFondo(Base):
    __tablename__ = "liquidacion_fondos"
    __table_args__ = (
        CheckConstraint("monto_general >= 0", name="ck_liquidacion_fondo_monto"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    anio: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    monto_general: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())


class LiquidacionPago(Base):
    __tablename__ = "liquidacion_pagos"
    __table_args__ = (
        UniqueConstraint("anio", "socio_id", name="uq_liquidacion_pago_anio_socio"),
        CheckConstraint("monto >= 0", name="ck_liquidacion_pago_monto"),
        CheckConstraint("metodo_pago IS NULL OR metodo_pago IN ('EFECTIVO','TRANSFERENCIA')", name="ck_liquidacion_pago_metodo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    anio: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    socio_id: Mapped[int] = mapped_column(ForeignKey("socios.id", ondelete="CASCADE"), nullable=False, index=True)
    # Copia del nombre y del neto al momento del pago (comprobante histórico).
    nombre_socio: Mapped[str] = mapped_column(String(150), nullable=False)
    monto: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # Pagos anteriores conservan su método (EFECTIVO/TRANSFERENCIA). Desde el botón
    # "Ya se liquidó" no se registra método: queda NULL y solo cuenta que se liquidó.
    metodo_pago: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    fecha_pago: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    usuario_nombre: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    def __repr__(self) -> str:
        return f"<LiquidacionPago(anio={self.anio}, socio_id={self.socio_id}, monto={self.monto})>"
