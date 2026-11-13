"""Control de pagos de la Liquidación anual (/finanzas/liquidacion-anual/...).

Reglas:
- El neto a pagar SIEMPRE lo calcula el backend con FinanzasService.calcular_liquidacion_anual
  (las fórmulas no cambian); el cliente solo indica socio y año ("Ya se liquidó").
  No se registra método de pago: solo que la liquidación ya se realizó.
- El dinero general del año vive en liquidacion_fondos. Su fila se bloquea con
  SELECT ... FOR UPDATE en cada pago, reversión o ajuste, de modo que dos operaciones
  simultáneas del mismo año se ejecutan una detrás de otra.
- La restricción única (anio, socio_id) impide liquidar dos veces al mismo socio
  aunque dos peticiones lleguen al mismo tiempo.
- Saldo disponible = dinero general - suma de pagos. Revertir un pago lo borra y el
  saldo se restaura solo.
"""
from decimal import Decimal
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.periodos import anio_del_periodo
from app.core.database import get_db
from app.core.deps import get_current_active_admin, get_current_user
from app.models.liquidacion import LiquidacionFondo, LiquidacionPago
from app.models.usuario import Usuario
from app.schemas.finanzas import LiquidacionAnualResponse
from app.schemas.liquidacion_pago import (
    LiquidacionControlItem,
    LiquidacionControlResponse,
    LiquidacionFondoUpdate,
    LiquidacionPagoCreate,
    LiquidacionPagoResponse,
)
from app.services.finanzas_service import FinanzasService
from app.services.historial_service import registrar_movimiento

router = APIRouter(prefix="/finanzas/liquidacion-anual", tags=["Liquidación anual - Pagos"])

CERO = Decimal("0.00")
MODULO = "Liquidación"


def _monto_general_sugerido(liquidacion: LiquidacionAnualResponse) -> Decimal:
    """Dinero necesario para pagar a todos: suma de los netos positivos del año."""
    return sum((max(CERO, s.total_neto_entregar) for s in liquidacion.socios_liquidados), CERO)


def _monto_utilizado(db: Session, anio: int) -> Decimal:
    return db.execute(
        select(func.coalesce(func.sum(LiquidacionPago.monto), CERO)).where(LiquidacionPago.anio == anio)
    ).scalar_one()


def _fondo_bloqueado(db: Session, anio: int, monto_inicial: Optional[Decimal]) -> LiquidacionFondo:
    """Devuelve la fila del fondo del año bloqueada; la crea si aún no existe."""
    stmt = select(LiquidacionFondo).where(LiquidacionFondo.anio == anio).with_for_update()
    fondo = db.execute(stmt).scalar_one_or_none()
    if fondo is not None:
        return fondo
    if monto_inicial is None:
        monto_inicial = _monto_general_sugerido(FinanzasService.calcular_liquidacion_anual(db, anio))
    try:
        with db.begin_nested():
            fondo = LiquidacionFondo(anio=anio, monto_general=monto_inicial)
            db.add(fondo)
            db.flush()
    except IntegrityError:
        # Otra petición lo creó al mismo tiempo: tomar el suyo (espera su commit).
        fondo = db.execute(stmt).scalar_one()
    return fondo


def _commit(db: Session, detalle_conflicto: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle_conflicto)


@router.get("/control", response_model=LiquidacionControlResponse, summary="Estado de pagos de la liquidación y saldo del fondo")
def get_control_liquidacion(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Session = Depends(get_db),
    anio: Optional[int] = Query(None, ge=2000, le=2100),
) -> LiquidacionControlResponse:
    anio = anio or anio_del_periodo(db)
    liquidacion = FinanzasService.calcular_liquidacion_anual(db, anio)
    fondo = db.execute(select(LiquidacionFondo).where(LiquidacionFondo.anio == anio)).scalar_one_or_none()
    pagos = {
        p.socio_id: p for p in db.execute(
            select(LiquidacionPago).where(LiquidacionPago.anio == anio)
        ).scalars()
    }
    monto_general = fondo.monto_general if fondo else _monto_general_sugerido(liquidacion)
    monto_utilizado = sum((p.monto for p in pagos.values()), CERO)

    items: list[LiquidacionControlItem] = []
    for s in liquidacion.socios_liquidados:
        pago = pagos.pop(s.socio_id, None)
        items.append(LiquidacionControlItem(
            socio_id=s.socio_id, nombre=s.nombre, cedula=s.cedula, activo=s.activo,
            total_neto_entregar=s.total_neto_entregar, liquidado=pago is not None,
            pago=LiquidacionPagoResponse.model_validate(pago) if pago else None,
        ))
    # Pagos de socios que ya no aparecen en el cálculo: se muestran igual, son dinero entregado.
    for pago in pagos.values():
        items.append(LiquidacionControlItem(
            socio_id=pago.socio_id, nombre=pago.nombre_socio, liquidado=True,
            pago=LiquidacionPagoResponse.model_validate(pago),
        ))

    total_liquidados = sum(1 for item in items if item.liquidado)
    return LiquidacionControlResponse(
        anio=anio,
        monto_general=monto_general,
        fondo_definido=fondo is not None,
        monto_utilizado=monto_utilizado,
        saldo_disponible=monto_general - monto_utilizado,
        total_socios=len(items),
        total_liquidados=total_liquidados,
        total_pendientes=len(items) - total_liquidados,
        socios=items,
    )


@router.post("/pagos", response_model=LiquidacionPagoResponse, status_code=status.HTTP_201_CREATED,
             summary="Ya se liquidó: marcar que el socio recibió su liquidación")
def registrar_pago_liquidacion(
    pago_in: LiquidacionPagoCreate,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db),
) -> LiquidacionPago:
    liquidacion = FinanzasService.calcular_liquidacion_anual(db, pago_in.anio)
    socio = next((s for s in liquidacion.socios_liquidados if s.socio_id == pago_in.socio_id), None)
    if socio is None:
        raise HTTPException(status_code=404, detail="El socio no hace parte de la liquidación de ese año")
    if socio.total_neto_entregar < CERO:
        raise HTTPException(
            status_code=400,
            detail="El socio debe dinero a la natillera; no tiene valor a recibir en la liquidación",
        )

    # Desde aquí las operaciones del mismo año quedan en fila (bloqueo del fondo).
    fondo = _fondo_bloqueado(db, pago_in.anio, _monto_general_sugerido(liquidacion))

    ya_pagado = db.execute(select(LiquidacionPago.id).where(
        LiquidacionPago.anio == pago_in.anio, LiquidacionPago.socio_id == pago_in.socio_id,
    )).scalar_one_or_none()
    if ya_pagado is not None:
        db.rollback()
        raise HTTPException(status_code=409, detail="Este socio ya fue liquidado")

    saldo = fondo.monto_general - _monto_utilizado(db, pago_in.anio)
    if socio.total_neto_entregar > saldo:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Saldo insuficiente: quedan ${saldo:,.2f} y la liquidación del socio es ${socio.total_neto_entregar:,.2f}",
        )

    pago = LiquidacionPago(
        anio=pago_in.anio,
        socio_id=socio.socio_id,
        nombre_socio=socio.nombre,
        monto=socio.total_neto_entregar,
        metodo_pago=None,
        usuario_nombre=current_user.nombre_completo or current_user.username,
    )
    db.add(pago)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Este socio ya fue liquidado")
    registrar_movimiento(
        db, MODULO, "CREAR",
        f"Liquidación {pago.anio} de {pago.nombre_socio} marcada como liquidada (${pago.monto:,.2f})",
        "LiquidacionPago", pago.id, datos_nuevos=pago, usuario=current_user,
    )
    _commit(db, "Este socio ya fue liquidado")
    db.refresh(pago)
    return pago


@router.delete("/pagos/{pago_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Revertir el pago de una liquidación")
def revertir_pago_liquidacion(
    pago_id: int,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db),
) -> None:
    pago = db.get(LiquidacionPago, pago_id)
    if pago is None:
        raise HTTPException(status_code=404, detail="Pago de liquidación no encontrado")
    _fondo_bloqueado(db, pago.anio, None)
    pago = db.execute(select(LiquidacionPago).where(LiquidacionPago.id == pago_id).with_for_update()).scalar_one_or_none()
    if pago is None:  # Otra petición ya lo revirtió.
        db.rollback()
        raise HTTPException(status_code=404, detail="Pago de liquidación no encontrado")
    registrar_movimiento(
        db, MODULO, "ELIMINAR",
        f"Reversión de la liquidación {pago.anio} de {pago.nombre_socio} (${pago.monto:,.2f} vuelven al saldo)",
        "LiquidacionPago", pago.id, datos_previos=pago, usuario=current_user,
    )
    db.delete(pago)
    _commit(db, "No se pudo revertir el pago")


@router.put("/fondo", response_model=LiquidacionControlResponse, summary="Ajustar el dinero general destinado a la liquidación")
def actualizar_fondo(
    fondo_in: LiquidacionFondoUpdate,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db),
) -> LiquidacionControlResponse:
    fondo = _fondo_bloqueado(db, fondo_in.anio, fondo_in.monto_general)
    utilizado = _monto_utilizado(db, fondo_in.anio)
    if fondo_in.monto_general < utilizado:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"El dinero general no puede ser menor a lo ya entregado (${utilizado:,.2f})",
        )
    anterior = fondo.monto_general
    fondo.monto_general = fondo_in.monto_general
    registrar_movimiento(
        db, MODULO, "EDITAR",
        f"Dinero general de la liquidación {fondo.anio}: ${anterior:,.2f} → ${fondo.monto_general:,.2f}",
        "LiquidacionFondo", fondo.id, datos_previos={"monto_general": anterior},
        datos_nuevos={"monto_general": fondo.monto_general}, usuario=current_user,
    )
    _commit(db, "No se pudo actualizar el dinero general")
    return get_control_liquidacion(current_user, db, fondo_in.anio)
