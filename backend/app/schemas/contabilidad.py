"""Esquemas Pydantic para Contabilidad (arqueo de cuentas)."""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CuentaBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=120, description="Cuenta o lugar donde está el dinero")
    valor: Decimal = Field(..., max_digits=14, decimal_places=2, ge=0, description="Valor disponible")

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("El nombre de la cuenta no puede estar vacío")
        return valor


class CuentaCreate(CuentaBase):
    model_config = ConfigDict(extra="forbid")


class CuentaResponse(CuentaBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DesgloseEsperado(BaseModel):
    """Cómo se obtiene el dinero que debería existir en caja."""
    capital_total: Decimal
    cartera_prestada: Decimal
    liquidez_sistema: Decimal
    gastos_generales: Decimal
    liquidaciones_pagadas: Decimal
    dinero_esperado: Decimal


class ContabilidadActual(BaseModel):
    dinero_esperado: Decimal
    desglose: DesgloseEsperado
    cuentas: List[CuentaResponse]
    total_cuentas: Decimal
    diferencia: Decimal
    resultado: str


class RegistroCreate(BaseModel):
    observacion: Optional[str] = Field(None, max_length=500)

    model_config = ConfigDict(extra="forbid")


class RegistroCuentaResponse(BaseModel):
    orden: int
    nombre: str
    valor: Decimal

    model_config = ConfigDict(from_attributes=True)


class RegistroResponse(BaseModel):
    id: int
    fecha_registro: datetime
    dinero_esperado: Decimal
    total_cuentas: Decimal
    diferencia: Decimal
    resultado: str
    desglose_esperado: Optional[dict] = None
    observacion: Optional[str] = None
    usuario_nombre: Optional[str] = None
    cuentas: List[RegistroCuentaResponse] = []

    model_config = ConfigDict(from_attributes=True)
