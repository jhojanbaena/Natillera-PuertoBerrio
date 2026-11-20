"""Configuración de "Permitir vista a los socios" (apartado Panel, rol Desarrollador).

Una sola fila (id = 1) en el esquema común, compartida por todos los años.
Si la fila no existe, el acceso de los socios está desactivado.

- TODOS: todos los socios activos, incluidos los que se registren después.
- RANGO: solo los socios con ID real entre id_inicio e id_fin (ambos incluidos).
- DESACTIVADO: nadie entra; al desactivar, `version` aumenta y las sesiones
  abiertas dejan de servir aunque luego se vuelva a habilitar el acceso.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, SCHEMA_COMUN

MODO_TODOS = "TODOS"
MODO_RANGO = "RANGO"
MODO_DESACTIVADO = "DESACTIVADO"
MODOS = (MODO_TODOS, MODO_RANGO, MODO_DESACTIVADO)


class ConfigVistaSocios(Base):
    __tablename__ = "config_vista_socios"
    __table_args__ = (
        CheckConstraint("modo IN ('TODOS', 'RANGO', 'DESACTIVADO')", name="ck_vista_socios_modo"),
        CheckConstraint(
            "modo <> 'RANGO' OR (id_inicio IS NOT NULL AND id_fin IS NOT NULL AND id_inicio >= 1 AND id_fin >= id_inicio)",
            name="ck_vista_socios_rango",
        ),
        {"schema": SCHEMA_COMUN},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    modo: Mapped[str] = mapped_column(String(20), nullable=False, default=MODO_DESACTIVADO)
    id_inicio: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    id_fin: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Aumenta cada vez que se quita el acceso: invalida los tokens de socio emitidos antes.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    usuario_nombre: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ConfigVistaSocios(modo={self.modo}, rango={self.id_inicio}-{self.id_fin}, version={self.version})>"
