"""Modelo ORM para Finanzas y Registro Transaccional de Socios (Aportes, Multas)."""
from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING
import enum
from sqlalchemy import String, Numeric, DateTime, ForeignKey, Index, func, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.socio import Socio


class TipoMovimientoFinanciero(str, enum.Enum):
    APORTE = "APORTE"
    MULTA = "MULTA"
    PAGO_MULTA = "PAGO_MULTA"
    RETIRO_AHORRO = "RETIRO_AHORRO"


class FinanzaSocio(Base):
    __tablename__ = "finanzas_socio"
    __table_args__ = (
        # Un mismo mes (AAAA-MM) solo puede tener un aporte mensual por socio.
        Index("uq_finanza_aporte_periodo", "socio_id", "tipo_movimiento", "periodo", unique=True),
        # Una multa solo puede tener un pago vinculado.
        Index("uq_finanza_pago_multa", "multa_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    socio_id: Mapped[int] = mapped_column(
        ForeignKey("socios.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    tipo_movimiento: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True
    )
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(255), nullable=True)
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    # Mes al que corresponde un aporte mensual ("AAAA-MM"); nulo en movimientos libres.
    periodo: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    # En un PAGO_MULTA, la multa que salda; nulo en pagos sin multa asociada.
    multa_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("finanzas_socio.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relación inversa
    socio: Mapped["Socio"] = relationship("Socio", back_populates="finanzas")

    def __repr__(self) -> str:
        return f"<FinanzaSocio(id={self.id}, socio_id={self.socio_id}, tipo='{self.tipo_movimiento}', monto={self.monto})>"
