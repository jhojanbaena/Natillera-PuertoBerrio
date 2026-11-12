"""Modelos ORM para Préstamos y Abonos de Cuotas."""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, TYPE_CHECKING
import enum
from sqlalchemy import String, Numeric, Integer, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.socio import Socio


class EstadoPrestamo(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    PAGADO = "PAGADO"
    EN_MORA = "EN_MORA"


# Préstamos que ya no tienen capital en la calle.
ESTADOS_CERRADOS = (EstadoPrestamo.PAGADO.value,)


class ReglaInteres(str, enum.Enum):
    # Tasa mensual fija pactada (préstamos anteriores a la regla 7 % / 10 %).
    FIJA = "FIJA"
    # 7 % mensual si se paga a tiempo; 10 % si se paga después de la fecha límite.
    MORA_7_10 = "MORA_7_10"
    # 10 % mensual sobre el capital pendiente: 7 % para el socio y 3 % para el bien común.
    # Sigue causando intereses cada mes mientras quede capital por pagar.
    REPARTO_7_3 = "REPARTO_7_3"


class Prestamo(Base):
    __tablename__ = "prestamos"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    socio_id: Mapped[int] = mapped_column(
        ForeignKey("socios.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    monto_prestado: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tasa_interes: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0.0)
    total_intereses: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    saldo_pendiente: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    numero_cuotas: Mapped[int] = mapped_column(Integer, nullable=False)
    cuotas_pagadas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoPrestamo.PENDIENTE.value, nullable=False, index=True)
    fecha_prestamo: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=True)
    regla_interes: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ReglaInteres.FIJA.value, server_default=ReglaInteres.FIJA.value
    )
    tasa_mora: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Relaciones
    socio: Mapped["Socio"] = relationship("Socio", back_populates="prestamos")
    abonos: Mapped[List["AbonoPrestamo"]] = relationship(
        "AbonoPrestamo",
        back_populates="prestamo",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Prestamo(id={self.id}, socio_id={self.socio_id}, monto={self.monto_prestado}, saldo={self.saldo_pendiente})>"


class AbonoPrestamo(Base):
    __tablename__ = "abonos_prestamo"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    prestamo_id: Mapped[int] = mapped_column(
        ForeignKey("prestamos.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    monto_abonado: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    monto_capital: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    monto_interes: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    numero_cuota: Mapped[int] = mapped_column(Integer, nullable=False)
    # Solo en préstamos con regla 7 % / 10 %; NULL en abonos anteriores.
    tasa_aplicada: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    fecha_limite: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    dias_retraso: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Regla 7 % / 3 %: parte del interés que va al bien común (el resto es del socio).
    # NULL en abonos anteriores, que conservan la regla de la cuota >= 4.
    interes_bien_comun: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    fecha_pago: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Relación inversa
    prestamo: Mapped["Prestamo"] = relationship("Prestamo", back_populates="abonos")

    def __repr__(self) -> str:
        return f"<AbonoPrestamo(id={self.id}, prestamo_id={self.prestamo_id}, cuota={self.numero_cuota}, monto={self.monto_abonado})>"

