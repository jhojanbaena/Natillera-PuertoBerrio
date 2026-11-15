"""Modelo ORM de las actividades registradas a cada socio (apartado Actividades del socio).

Cada línea es lo que el socio vendió o ganó en una actividad: tipo (rifa interna
u otra), nombre, mes (solo rifa interna), cantidad vendida (opcional) y ganancia.
En la hoja imprimible las rifas internas van en su mes (columna R. interna) y las
demás en la columna Actividad; en el Total ahorrado suman como "Ganancias en rifa
interna" y "Ganancias en actividades".
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class TipoActividadSocio:
    RIFA_INTERNA = "RIFA_INTERNA"
    OTRA = "OTRA"


class ActividadSocio(Base):
    __tablename__ = "actividades_socio"
    __table_args__ = (
        CheckConstraint(
            "ganancia >= 0 AND (cantidad_vendida IS NULL OR cantidad_vendida >= 0)",
            name="ck_actividad_socio_valores",
        ),
        CheckConstraint(
            "tipo IN ('RIFA_INTERNA','OTRA') AND (mes IS NULL OR (mes >= 1 AND mes <= 12))",
            name="ck_actividad_socio_tipo",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    socio_id: Mapped[int] = mapped_column(ForeignKey("socios.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TipoActividadSocio.OTRA, server_default=TipoActividadSocio.OTRA,
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    # Mes (1-12) del año en que se hizo la rifa interna; NULL en las demás actividades.
    mes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cantidad_vendida: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ganancia: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())

    def __repr__(self) -> str:
        return f"<ActividadSocio(id={self.id}, socio_id={self.socio_id}, nombre='{self.nombre}', ganancia={self.ganancia})>"
