"""Modelo ORM de Periodos (años) de la natillera.

Cada año guarda sus datos en un esquema propio de la base de datos con el mismo
juego de tablas (socios, aportes, préstamos, abonos, gastos, contabilidad,
liquidación, historial...). Así los años nunca se mezclan y consultar un año
anterior no puede modificarlo.

- esquema NULL: el año original (2026), que conserva sus datos donde siempre
  estuvieron; la actualización no mueve ni borra ningún registro.
- Solo un periodo puede estar activo: es el que recibe los registros nuevos.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, SCHEMA_COMUN


class Periodo(Base):
    __tablename__ = "periodos"
    __table_args__ = (
        # Garantiza un único año activo a nivel de base de datos.
        Index(
            "uq_periodo_activo", "activo", unique=True,
            postgresql_where=text("activo"), sqlite_where=text("activo"),
        ),
        {"schema": SCHEMA_COMUN},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # unique: impide crear dos veces el mismo año.
    anio: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    esquema: Mapped[Optional[str]] = mapped_column(String(63), nullable=True, unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    copiado_de_anio: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    socios_copiados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usuario_nombre: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Periodo(anio={self.anio}, activo={self.activo})>"
