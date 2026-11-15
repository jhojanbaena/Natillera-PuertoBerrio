"""Esquemas Pydantic para el control de pagos de la Liquidación anual."""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class LiquidacionPagoCreate(BaseModel):
    """Botón "Ya se liquidó": solo indica que el socio recibió su liquidación.

    No se registra método de pago (efectivo/transferencia).
    """
    anio: int = Field(..., ge=2000, le=2100)
    socio_id: int = Field(..., ge=1)


class LiquidacionFondoUpdate(BaseModel):
    anio: int = Field(..., ge=2000, le=2100)
    monto_general: Decimal = Field(..., ge=0, max_digits=14, decimal_places=2)


class LiquidacionPagoResponse(BaseModel):
    id: int
    anio: int
    socio_id: int
    nombre_socio: str
    monto: Decimal
    # Solo en pagos registrados antes del botón "Ya se liquidó" (histórico).
    metodo_pago: Optional[str] = None
    fecha_pago: datetime
    usuario_nombre: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class LiquidacionControlItem(BaseModel):
    socio_id: int
    nombre: str
    cedula: Optional[str] = None
    activo: bool = True
    # Neto que arroja hoy el cálculo de la liquidación (None si ya no aparece en él).
    total_neto_entregar: Optional[Decimal] = None
    liquidado: bool = False
    pago: Optional[LiquidacionPagoResponse] = None


class LiquidacionControlResponse(BaseModel):
    anio: int
    monto_general: Decimal
    fondo_definido: bool
    monto_utilizado: Decimal
    saldo_disponible: Decimal
    total_socios: int
    total_liquidados: int
    total_pendientes: int
    socios: list[LiquidacionControlItem]
