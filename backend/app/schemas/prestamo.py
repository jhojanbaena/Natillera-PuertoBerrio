"""Esquemas de validación Pydantic para Préstamos y Abonos de Cuotas."""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator
from app.models.prestamo import EstadoPrestamo, ReglaInteres
from app.services import prestamos_service


class AbonoPrestamoCreate(BaseModel):
    prestamo_id: int = Field(..., description="ID del préstamo a abonar")
    monto_abonado: Decimal = Field(..., max_digits=12, decimal_places=2, gt=0, description="Monto total entregado en el abono")
    monto_capital: Optional[Decimal] = Field(None, max_digits=12, decimal_places=2, ge=0, description="Porción destinada a amortizar capital")
    monto_interes: Optional[Decimal] = Field(None, max_digits=12, decimal_places=2, ge=0, description="Porción destinada a cubrir interés")
    numero_cuota: Optional[int] = Field(None, ge=1, description="Número de cuota correspondiente")
    fecha_pago: Optional[date] = Field(None, description="Día en que se recibió el pago (pasado, hoy o futuro); por defecto hoy")
    tasa_aplicada: Optional[Decimal] = Field(
        None, max_digits=5, decimal_places=2, ge=0,
        description="Regla 7 %/10 %: tasa elegida por el administrador; si se omite se usa la sugerida por la fecha. Regla 7 %/3 %: siempre 10 %",
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_breakdown(self) -> "AbonoPrestamoCreate":
        if self.monto_capital is not None:
            monto_interes = self.monto_interes or Decimal("0.00")
            if self.monto_capital + monto_interes != self.monto_abonado:
                raise ValueError("El capital y el interés deben sumar exactamente el monto abonado")
        return self


class AbonoPrestamoResponse(BaseModel):
    id: int
    prestamo_id: int
    monto_abonado: Decimal
    monto_capital: Decimal
    monto_interes: Decimal
    numero_cuota: int
    fecha_pago: datetime
    tasa_aplicada: Optional[Decimal] = None
    fecha_limite: Optional[date] = None
    dias_retraso: Optional[int] = None
    # Regla 7 % / 3 %: parte del interés para el bien común (el resto es del socio).
    interes_bien_comun: Optional[Decimal] = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def interes_socio(self) -> Optional[Decimal]:
        if self.interes_bien_comun is None:
            return None
        return self.monto_interes - self.interes_bien_comun


class PeriodoInteresResponse(BaseModel):
    indice: int
    numero_cuota: int
    fecha_limite: date
    tasa: Decimal
    valor: Decimal
    pagado: Decimal
    pendiente: Decimal
    vencido: bool
    destino: str
    estado: str
    base: Decimal = Decimal("0.00")
    inicio: Optional[date] = None
    interes_socio: Decimal = Decimal("0.00")
    interes_bien_comun: Decimal = Decimal("0.00")


class PrestamoBase(BaseModel):
    socio_id: int = Field(..., description="ID del socio solicitante")
    monto_prestado: Decimal = Field(..., max_digits=12, decimal_places=2, gt=0, description="Capital total prestado")
    tasa_interes: Decimal = Field(default=Decimal("0.0"), max_digits=5, decimal_places=2, ge=0, description="Tasa de interés acordada en porcentaje")
    numero_cuotas: int = Field(..., gt=0, description="Número total de cuotas pactadas")
    fecha_prestamo: Optional[date] = Field(None, description="Fecha de desembolso")
    fecha_vencimiento: Optional[date] = Field(None, description="Fecha límite de pago")


class PrestamoCreate(PrestamoBase):
    regla_interes: ReglaInteres = Field(
        default=ReglaInteres.REPARTO_7_3,
        description=(
            "REPARTO_7_3 (por defecto): 10 % mensual sobre el capital pendiente, 7 % socio y 3 % bien común. "
            "MORA_7_10: 7 % a tiempo y 10 % con retraso (regla anterior). FIJA: tasa_interes fija."
        ),
    )


class PrestamoResponse(PrestamoBase):
    id: int
    total_intereses: Decimal
    saldo_pendiente: Decimal
    cuotas_pagadas: int
    estado: EstadoPrestamo
    fecha_prestamo: date
    created_at: datetime
    regla_interes: str = ReglaInteres.FIJA.value
    tasa_mora: Optional[Decimal] = None
    abonos: List[AbonoPrestamoResponse] = []

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def cuotas_atrasadas(self) -> int:
        return prestamos_service.cuotas_atrasadas(self)

    @computed_field
    @property
    def fecha_proxima_cuota(self) -> Optional[date]:
        return prestamos_service.fecha_proxima_cuota(self)

    @computed_field
    @property
    def intereses_pagados(self) -> Decimal:
        return sum((a.monto_interes for a in self.abonos), Decimal("0.00"))

    @computed_field
    @property
    def intereses_pendientes(self) -> Decimal:
        """Intereses de meses vencidos aún sin pagar."""
        return prestamos_service.intereses_pendientes_vencidos(self)

    @computed_field
    @property
    def tasa_vigente(self) -> Optional[Decimal]:
        """Tasa que corresponde si el próximo mes pendiente se paga hoy (regla 7 %/10 %)."""
        if not prestamos_service.es_regla_mora(self) or self.estado.value in prestamos_service.ESTADOS_CERRADOS:
            return None
        pendiente = next((p for p in self.periodos if p.pendiente > 0), None)
        if pendiente is None:
            return None
        tasa, _, _ = prestamos_service.tasa_sugerida(self, pendiente.fecha_limite, prestamos_service.hoy_colombia())
        return tasa

    @computed_field
    @property
    def periodos(self) -> List[PeriodoInteresResponse]:
        if not prestamos_service.es_regla_mora(self):
            return []
        return [
            PeriodoInteresResponse(**{
                **p.__dict__, "estado": p.estado,
                "interes_socio": p.interes_socio, "interes_bien_comun": p.interes_bien_comun,
            })
            for p in prestamos_service.periodos_interes(self)
        ]


class CuotaDisponible(BaseModel):
    numero_cuota: int
    fecha_limite: date
    # True si la cuota se agregó porque la fecha del abono pasó la última cuota.
    nueva: bool = False
    pagada: bool = False


class AbonoVistaPrevia(BaseModel):
    """Cálculo previo de un abono con regla 7 % / 10 % (no guarda nada)."""
    numero_cuota: int
    fecha_limite: date
    fecha_pago: date
    dias_retraso: int
    tasa_sugerida: Decimal
    motivo: str
    tasa_normal: Decimal
    tasa_mora: Decimal
    interes_tasa_normal: Decimal
    interes_tasa_mora: Decimal
    interes_pagado: Decimal
    pendiente_tasa_normal: Decimal
    pendiente_tasa_mora: Decimal
    tasa_elegida_previa: Optional[Decimal] = None
    destino: str
    saldo_capital: Decimal
    cuotas_disponibles: List[int]
    cuotas: List[CuotaDisponible] = []
    cuota_nueva: Optional[int] = None
    regla_interes: Optional[str] = None
    capital_base: Optional[Decimal] = None
    interes_socio: Optional[Decimal] = None
    interes_bien_comun: Optional[Decimal] = None


class ResumenPrestamoSocio(BaseModel):
    socio_id: int
    cedula: str
    nombre: str
    total_prestamos: int
    saldo_pendiente_total: Decimal
