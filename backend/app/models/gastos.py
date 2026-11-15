"""Modelo ORM de Gastos Generales de la natillera.

Cada gasto pertenece a un año (ciclo de liquidación). En la liquidación de ese año
el total se reparte en partes iguales entre los socios activos y se descuenta del
neto de cada uno. El valor por socio nunca se guarda: siempre se calcula desde los
gastos registrados, así no se descuenta dos veces y se ajusta si cambian los
socios activos.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class GastoGeneral(Base):
    __tablename__ = "gastos_generales"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    anio: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    descripcion: Mapped[str] = mapped_column(String(150), nullable=False)
    monto: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())

    def __repr__(self) -> str:
        return f"<GastoGeneral(id={self.id}, anio={self.anio}, monto={self.monto})>"
