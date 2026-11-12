"""Modelos ORM de Contabilidad (arqueo del dinero de la natillera).

- ContabilidadCuenta: dónde está guardado hoy el dinero (banco, efectivo, ...).
  Son las líneas editables del apartado.
- ContabilidadRegistro: fotografía guardada con "GUARDAR REGISTRO". Copia el dinero
  esperado según el sistema, el total contado, la diferencia y el resultado.
- ContabilidadRegistroCuenta: copia de cada cuenta en ese momento. No tiene llave
  hacia ContabilidadCuenta, así editar o borrar cuentas actuales no cambia el
  historial.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class ResultadoContabilidad:
    CUADRADA = "CUADRADA"
    FALTANTE = "FALTANTE"
    SOBRANTE = "SOBRANTE"


class ContabilidadCuenta(Base):
    __tablename__ = "contabilidad_cuentas"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())


class ContabilidadRegistro(Base):
    __tablename__ = "contabilidad_registros"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    dinero_esperado: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_cuentas: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # total_cuentas - dinero_esperado: negativo = faltante, positivo = sobrante.
    diferencia: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    resultado: Mapped[str] = mapped_column(String(20), nullable=False)
    # Cómo se obtuvo el dinero esperado en ese momento (copia, solo lectura).
    desglose_esperado: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    observacion: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    usuario_nombre: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    cuentas: Mapped[List["ContabilidadRegistroCuenta"]] = relationship(
        "ContabilidadRegistroCuenta",
        back_populates="registro",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ContabilidadRegistroCuenta.orden",
    )


class ContabilidadRegistroCuenta(Base):
    __tablename__ = "contabilidad_registro_cuentas"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    registro_id: Mapped[int] = mapped_column(
        ForeignKey("contabilidad_registros.id", ondelete="CASCADE"), nullable=False, index=True
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    registro: Mapped["ContabilidadRegistro"] = relationship("ContabilidadRegistro", back_populates="cuentas")
