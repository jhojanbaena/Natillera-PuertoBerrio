"""Esquemas de validación Pydantic para Finanzas y Transacciones de Socios."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.finanzas import TipoMovimientoFinanciero


class FinanzaBase(BaseModel):
    tipo_movimiento: TipoMovimientoFinanciero = Field(..., description="APORTE, MULTA, PAGO_MULTA o RETIRO_AHORRO")
    monto: Decimal = Field(..., max_digits=12, decimal_places=2, gt=0, description="Monto monetario del movimiento")
    descripcion: Optional[str] = Field(None, max_length=255, description="Detalle del movimiento")


class FinanzaMovimientoCreate(FinanzaBase):
    fecha: Optional[date] = Field(None, description="Día en que ocurrió el movimiento; por defecto hoy")
    periodo: Optional[str] = Field(
        None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Solo APORTE: mes (AAAA-MM) del aporte mensual; impide registrarlo dos veces",
    )
    multa_id: Optional[int] = Field(
        None, ge=1, description="Solo PAGO_MULTA: multa que se salda con este pago",
    )


class MultaUpdate(BaseModel):
    """Edición de una multa pendiente antes de registrar su pago."""
    monto: Optional[Decimal] = Field(None, max_digits=12, decimal_places=2, gt=0)
    descripcion: Optional[str] = Field(None, max_length=255)


class MultaEstadoItem(BaseModel):
    """Multa individual con su estado de pago."""
    id: int
    monto: Decimal
    descripcion: Optional[str] = None
    fecha: datetime
    pagada: bool = False
    pago_id: Optional[int] = None
    fecha_pago: Optional[datetime] = None


class FinanzaCreate(FinanzaBase):
    socio_id: int = Field(..., description="ID del socio al que pertenece la transacción")


class FinanzaResponse(FinanzaBase):
    id: int
    socio_id: int
    fecha: datetime
    periodo: Optional[str] = None
    multa_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class LiquidacionSocioItem(BaseModel):
    socio_id: int
    nombre: str
    cedula: str
    activo: bool = True
    total_ahorrado: Decimal
    porcentaje_participacion: Decimal
    utilidad_ganada: Decimal
    bien_comun_asignado: Decimal
    deuda_prestamos: Decimal
    multas_pendientes: Decimal
    # Liquidación antes de gastos generales y la parte de gastos que le corresponde.
    liquidacion_antes_gastos: Decimal = Decimal("0.00")
    gastos_generales: Decimal = Decimal("0.00")
    total_neto_entregar: Decimal


class LiquidacionAnualResponse(BaseModel):
    anio: int
    anios_disponibles: list[int] = []
    total_ahorro_acumulado: Decimal
    total_utilidades_generadas: Decimal
    total_bien_comun_general: Decimal
    rentabilidad_porcentual: Decimal
    total_deuda_descontada: Decimal
    total_multas_descontadas: Decimal
    total_gastos_generales: Decimal = Decimal("0.00")
    total_gastos_descontados: Decimal = Decimal("0.00")
    socios_activos: int = 0
    gran_total_a_entregar: Decimal
    socios_liquidados: list[LiquidacionSocioItem]

