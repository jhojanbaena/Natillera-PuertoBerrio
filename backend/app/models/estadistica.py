"""Modelo ORM de Estadísticas guardadas.

Cada fila es una fotografía: guarda los filtros elegidos y los resultados
calculados en el momento de guardarla. Los resultados nunca se recalculan, así
la estadística no cambia aunque después se registren nuevos movimientos.

Vive en el esquema común (compartido por todos los años) para poder consultarla
siempre, incluso desde otro año; `anio` indica de qué año son los datos.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, SCHEMA_COMUN


class EstadisticaGuardada(Base):
    __tablename__ = "estadisticas_guardadas"
    __table_args__ = {"schema": SCHEMA_COMUN}

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    anio: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    filtros: Mapped[dict] = mapped_column(JSON, nullable=False)
    resultados: Mapped[dict] = mapped_column(JSON, nullable=False)
    usuario_nombre: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<EstadisticaGuardada(id={self.id}, nombre='{self.nombre}', anio={self.anio})>"
