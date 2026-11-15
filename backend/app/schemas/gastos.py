"""Esquemas Pydantic para Gastos Generales."""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class GastoGeneralBase(BaseModel):
    descripcion: str = Field(..., min_length=1, max_length=150, description="Nombre o concepto del gasto")
    monto: Decimal = Field(..., max_digits=14, decimal_places=2, ge=0, description="Valor del gasto")

    @field_validator("descripcion")
    @classmethod
    def limpiar_descripcion(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("La descripción del gasto no puede estar vacía")
        return valor


class GastoGeneralCreate(GastoGeneralBase):
    anio: Optional[int] = Field(None, ge=2000, le=2100, description="Año de liquidación; por defecto el actual")

    model_config = ConfigDict(extra="forbid")


class GastoGeneralUpdate(GastoGeneralBase):
    model_config = ConfigDict(extra="forbid")


class GastoGeneralResponse(GastoGeneralBase):
    id: int
    anio: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class GastosGeneralesResumen(BaseModel):
    anio: int
    anios_disponibles: List[int]
    gastos: List[GastoGeneralResponse]
    total_gastos: Decimal
    socios_activos: int
    # total_gastos / socios_activos (0 si no hay socios activos).
    gasto_por_socio: Decimal
