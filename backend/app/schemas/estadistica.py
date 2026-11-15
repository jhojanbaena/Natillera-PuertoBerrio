"""Esquemas Pydantic de Estadísticas."""
from datetime import date, datetime
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.estadisticas_service import TIPOS_MOVIMIENTO

PATRON_EVENTO = r"^(actividad|rifa|reunion)-[0-9]{1,9}$"


class FiltrosEstadistica(BaseModel):
    modo: Literal["todo", "meses", "fechas"] = "todo"
    fecha_desde: Optional[date] = None
    fecha_hasta: Optional[date] = None
    evento: Optional[str] = Field(None, pattern=PATRON_EVENTO)
    tipos: List[str] = Field(default_factory=list, max_length=len(TIPOS_MOVIMIENTO))

    model_config = ConfigDict(extra="forbid")

    @field_validator("tipos")
    @classmethod
    def tipos_validos(cls, valores: List[str]) -> List[str]:
        desconocidos = [v for v in valores if v not in TIPOS_MOVIMIENTO]
        if desconocidos:
            raise ValueError(f"Tipo de movimiento desconocido: {', '.join(desconocidos)}")
        return list(dict.fromkeys(valores))

    @model_validator(mode="after")
    def rango_valido(self):
        if self.fecha_desde and self.fecha_hasta and self.fecha_hasta < self.fecha_desde:
            raise ValueError("La fecha final no puede ser anterior a la fecha inicial")
        return self


class EstadisticaGuardar(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=120)
    filtros: FiltrosEstadistica

    model_config = ConfigDict(extra="forbid")

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("El nombre de la estadística no puede estar vacío")
        return valor


class EstadisticaGuardadaResumen(BaseModel):
    id: int
    nombre: str
    anio: int
    filtros: dict[str, Any]
    totales: dict[str, Any]
    usuario_nombre: Optional[str] = None
    created_at: datetime


class EstadisticaGuardadaResponse(EstadisticaGuardadaResumen):
    resultados: dict[str, Any]
