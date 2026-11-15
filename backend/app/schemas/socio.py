"""Esquemas de validación Pydantic para Socios y su Perfil Integral."""
from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.finanzas import FinanzaResponse, MultaEstadoItem
from app.schemas.prestamo import PrestamoResponse


class SocioBase(BaseModel):
    cedula: str = Field(..., min_length=5, max_length=20, description="Cédula o documento de identidad único")
    nombre: str = Field(..., min_length=2, max_length=100, description="Nombre completo del socio")
    telefono: str = Field(..., min_length=7, max_length=20, description="Número de teléfono o celular")
    residencia: str = Field(..., min_length=3, max_length=200, description="Dirección o lugar de residencia")
    aporte_mensual: Decimal = Field(..., max_digits=12, decimal_places=2, ge=0, description="Cuota o aporte obligatorio mensual pactado")


class SocioCreate(SocioBase):
    id: Optional[int] = Field(None, ge=1, description="Identificador numérico del socio")


class SocioUpdate(BaseModel):
    id: Optional[int] = Field(None, ge=1, description="Nuevo ID identificativo del socio")
    cedula: Optional[str] = Field(None, min_length=5, max_length=20)
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    telefono: Optional[str] = Field(None, min_length=7, max_length=20)
    residencia: Optional[str] = Field(None, min_length=3, max_length=200)
    aporte_mensual: Optional[Decimal] = Field(None, max_digits=12, decimal_places=2, ge=0)
    is_active: Optional[bool] = None


class SocioResponse(SocioBase):
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ActividadSocioCreate(BaseModel):
    """Línea del apartado Actividades del socio.

    - RIFA_INTERNA: requiere el mes (1-12); el nombre es opcional ("Rifa interna").
    - OTRA: requiere el nombre de la actividad; no lleva mes.
    """
    tipo: Literal["RIFA_INTERNA", "OTRA"] = Field("OTRA", description="RIFA_INTERNA u OTRA")
    nombre: Optional[str] = Field(None, max_length=150, description="Nombre de la actividad (obligatorio en OTRA)")
    mes: Optional[int] = Field(None, ge=1, le=12, description="Mes de la rifa interna (1-12)")
    cantidad_vendida: Optional[int] = Field(None, ge=0, description="Cantidad vendida (opcional)")
    ganancia: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2, description="Ganancia del socio")

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validar_tipo(self) -> "ActividadSocioCreate":
        nombre = (self.nombre or "").strip()
        if self.tipo == "RIFA_INTERNA":
            if self.mes is None:
                raise ValueError("Indica el mes de la rifa interna")
            self.nombre = nombre or "Rifa interna"
        else:
            if not nombre:
                raise ValueError("Escribe el nombre de la actividad")
            self.nombre = nombre
            self.mes = None
        return self


class ActividadSocioResponse(BaseModel):
    id: int
    socio_id: int
    tipo: str = "OTRA"
    nombre: str
    mes: Optional[int] = None
    cantidad_vendida: Optional[int] = None
    ganancia: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeduccionPrestamoItem(BaseModel):
    """Lo que el socio debe hoy de un préstamo."""
    prestamo_id: int
    orden_socio: Optional[int] = None
    estado: str
    capital_pendiente: Decimal
    intereses_pendientes: Decimal
    total: Decimal


class DeduccionMultaItem(BaseModel):
    multa_id: int
    descripcion: Optional[str] = None
    fecha: datetime
    monto: Decimal


class DeduccionesSocio(BaseModel):
    """Todas las obligaciones económicas pendientes del socio."""
    prestamos: List[DeduccionPrestamoItem] = []
    multas: List[DeduccionMultaItem] = []
    total_capital_pendiente: Decimal = Decimal("0.00")
    total_intereses_pendientes: Decimal = Decimal("0.00")
    total_multas_pendientes: Decimal = Decimal("0.00")
    total_deducciones: Decimal = Decimal("0.00")


class TotalAhorradoSocio(BaseModel):
    """Ahorros y beneficios acumulados por el socio (sin duplicar conceptos)."""
    aportes_mensuales: Decimal = Decimal("0.00")
    ganancias_intereses: Decimal = Decimal("0.00")
    # Suma de las líneas del apartado Actividades del socio (tipo "Otra").
    ganancias_actividades: Decimal = Decimal("0.00")
    # Suma de las líneas de rifa interna del socio.
    ganancias_rifa_interna: Decimal = Decimal("0.00")
    # Parte del socio en las rifas grandes y pequeñas del apartado Eventos y Rifas.
    ganancias_rifas: Decimal = Decimal("0.00")
    ganancias_reuniones: Decimal = Decimal("0.00")
    bien_comun: Decimal = Decimal("0.00")
    total: Decimal = Decimal("0.00")
    activo: bool = True


class MovimientoPrestamoItem(BaseModel):
    """Movimiento de préstamo en el historial individual del socio."""
    clave: str
    # ABONO, PAGO (abono que cancela el préstamo), EDICION o REVERSION.
    tipo: str
    fecha: datetime
    prestamo_id: int
    abono_id: Optional[int] = None
    numero_cuota: Optional[int] = None
    monto: Decimal = Decimal("0.00")
    monto_capital: Optional[Decimal] = None
    monto_interes: Optional[Decimal] = None
    descripcion: str
    # False si el abono ya no existe (se revirtió) o la corrección se deshizo.
    vigente: bool = True


class SocioDetailResponse(SocioResponse):
    """Perfil detallado que consolida finanzas, multas y préstamos del socio."""
    total_ahorrado: Decimal = Decimal("0.00")
    total_multas_pendientes: Decimal = Decimal("0.00")
    total_multas_pagadas: Decimal = Decimal("0.00")
    total_prestamos_activos: int = 0
    saldo_prestamos_pendiente: Decimal = Decimal("0.00")
    historial_finanzas: List[FinanzaResponse] = []
    multas: List[MultaEstadoItem] = []
    prestamos: List[PrestamoResponse] = []
    deducciones: DeduccionesSocio = DeduccionesSocio()
    total_ahorrado_socio: TotalAhorradoSocio = TotalAhorradoSocio()
    movimientos_prestamos: List[MovimientoPrestamoItem] = []
    actividades: List[ActividadSocioResponse] = []

    model_config = ConfigDict(from_attributes=True)
