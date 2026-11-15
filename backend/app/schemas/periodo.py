"""Esquemas Pydantic del apartado Años (periodos)."""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field


class PeriodoActual(BaseModel):
    anio_activo: int
    anio_consultado: int
    solo_lectura: bool


class PeriodoResponse(BaseModel):
    anio: int
    activo: bool
    copiado_de_anio: Optional[int] = None
    socios_copiados: int = 0
    usuario_nombre: Optional[str] = None
    created_at: Optional[datetime] = None
    socios: int = 0
    socios_activos: int = 0
    total_ahorro: Decimal = Decimal("0")
    prestamos: int = 0
    total_prestado: Decimal = Decimal("0")
    total_gastos: Decimal = Decimal("0")


class PeriodosResponse(PeriodoActual):
    proximo_anio: int
    periodos: List[PeriodoResponse]


class PeriodoCreate(BaseModel):
    # Año que el usuario confirmó crear; debe ser exactamente el siguiente al último.
    anio: int = Field(..., ge=2000, le=2100)


class PeriodoCreado(BaseModel):
    anio: int
    copiado_de_anio: int
    socios_copiados: int
