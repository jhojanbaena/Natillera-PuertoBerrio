"""Router para la Gestión y Consolidación de Préstamos (/prestamos).
Cumple con el criterio RF9 (Consolidar dinero prestado global y lista detallada por socio con su saldo pendiente).
"""
from datetime import date
from decimal import Decimal
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.deps import get_current_active_admin, get_current_user
from app.models.usuario import Usuario
from app.models.socio import Socio
from app.models.prestamo import (
    Prestamo, AbonoPrestamo, EstadoPrestamo, ESTADOS_CERRADOS, ReglaInteres,
)
from app.services.historial_service import registrar_movimiento, model_to_dict
from app.services.prestamos_service import (
    CERO, TASA_MORA, TASA_NORMAL, TASA_REPARTO,
    calcular_abono_mora, cuota_por_defecto, es_regla_mora, es_regla_reparto, fecha_a_datetime, fecha_local, hoy_colombia,
    interes_mensual, parte_bien_comun, periodos_interes, recalcular_prestamo,
    sincronizar_moras, tasa_mora_de, tasa_sugerida, validar_fecha_abono,
)
from app.schemas.prestamo import (
    PrestamoCreate,
    PrestamoResponse,
    AbonoPrestamoCreate,
    AbonoPrestamoResponse,
    AbonoVistaPrevia,
    CuotaDisponible,
    ResumenPrestamoSocio,
)

router = APIRouter(prefix="/prestamos", tags=["Préstamos"])


def _prestamo_bloqueado(db: Session, prestamo_id: int) -> Prestamo:
    prestamo = db.execute(
        select(Prestamo).where(Prestamo.id == prestamo_id).with_for_update()
    ).scalar_one_or_none()
    if not prestamo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Préstamo con ID {prestamo_id} no encontrado",
        )
    return prestamo


@router.post("", response_model=PrestamoResponse, status_code=status.HTTP_201_CREATED, summary="Registrar un nuevo préstamo")
def create_prestamo(
    prestamo_in: PrestamoCreate,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db)
) -> Prestamo:
    """
    Registra un desembolso de préstamo para un socio.
    Calcula intereses proyectados y fija el saldo inicial pendiente.
    Con la regla REPARTO_7_3 (por defecto) la tasa es 10 % mensual sobre el capital
    pendiente: 7 % para el socio y 3 % para el bien común. Las reglas anteriores
    (MORA_7_10 y FIJA) se conservan para compatibilidad.
    """
    # Validar que el socio exista y esté activo
    stmt_socio = select(Socio).where(Socio.id == prestamo_in.socio_id)
    socio = db.execute(stmt_socio).scalar_one_or_none()

    if not socio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Socio con ID {prestamo_in.socio_id} no encontrado",
        )

    if not socio.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pueden emitir préstamos a un socio inactivo",
        )

    regla_mora = prestamo_in.regla_interes == ReglaInteres.MORA_7_10
    regla_reparto = prestamo_in.regla_interes == ReglaInteres.REPARTO_7_3
    if regla_reparto:
        tasa_interes = TASA_REPARTO
    else:
        tasa_interes = TASA_NORMAL if regla_mora else prestamo_in.tasa_interes
    # Calcular el interés mensual acumulado durante todas las cuotas pactadas.
    interes_mes = prestamo_in.monto_prestado * (tasa_interes / Decimal("100.0"))
    if regla_mora or regla_reparto:
        interes_mes = interes_mes.quantize(Decimal("0.01"))
    total_intereses = (interes_mes * prestamo_in.numero_cuotas).quantize(Decimal("0.01"))
    fecha_prestamo = prestamo_in.fecha_prestamo or date.today()

    db_prestamo = Prestamo(
        socio_id=prestamo_in.socio_id,
        monto_prestado=prestamo_in.monto_prestado,
        tasa_interes=tasa_interes,
        tasa_mora=TASA_MORA if regla_mora else None,
        regla_interes=prestamo_in.regla_interes.value,
        total_intereses=total_intereses,
        saldo_pendiente=prestamo_in.monto_prestado,  # Saldo de capital adeudado
        numero_cuotas=prestamo_in.numero_cuotas,
        cuotas_pagadas=0,
        estado=EstadoPrestamo.PENDIENTE.value,
        fecha_prestamo=fecha_prestamo,
        fecha_vencimiento=prestamo_in.fecha_vencimiento,
    )
    db.add(db_prestamo)
    db.flush()
    db.refresh(db_prestamo)
    if regla_reparto:
        # Un préstamo con fecha pasada puede tener ya meses causados fuera del plazo.
        recalcular_prestamo(db, db_prestamo)

    registrar_movimiento(
        db=db,
        modulo="Préstamos",
        tipo_accion="CREAR",
        descripcion=f"Préstamo #{db_prestamo.id} registrado para socio {socio.nombre} por ${db_prestamo.monto_prestado:,.2f}",
        entidad_tipo="Prestamo",
        entidad_id=db_prestamo.id,
        datos_nuevos=db_prestamo,
        usuario=current_user,
        commit_now=True
    )

    return db_prestamo


@router.get(
    "/{prestamo_id}/abonos/vista-previa",
    response_model=AbonoVistaPrevia,
    summary="Tasa sugerida (7 % o 10 %) e intereses de una cuota antes de registrar el abono",
)
def vista_previa_abono(
    prestamo_id: int,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Session = Depends(get_db),
    fecha_pago: Optional[date] = Query(None, description="Fecha del abono; por defecto hoy"),
    numero_cuota: Optional[int] = Query(None, ge=1, description="Cuota global; por defecto la primera pendiente"),
    excluir_abono_id: Optional[int] = Query(None, description="Abono en edición, que no se cuenta como pagado"),
) -> AbonoVistaPrevia:
    prestamo = db.execute(select(Prestamo).where(Prestamo.id == prestamo_id)).scalar_one_or_none()
    if not prestamo:
        raise HTTPException(status_code=404, detail=f"Préstamo con ID {prestamo_id} no encontrado")
    if not es_regla_mora(prestamo):
        raise HTTPException(status_code=400, detail="El préstamo usa tasa fija; no aplica la regla 7 % / 10 %")
    fecha = fecha_pago or hoy_colombia()
    periodos = periodos_interes(prestamo, excluir_abono_id=excluir_abono_id, hasta=fecha)
    if not periodos:
        raise HTTPException(status_code=400, detail="El préstamo no tiene meses de interés")
    if numero_cuota is not None:
        periodo = next((p for p in periodos if p.numero_cuota == numero_cuota), None)
        if periodo is None:
            raise HTTPException(status_code=422, detail="La cuota no pertenece a este préstamo")
    else:
        periodo = cuota_por_defecto(periodos)
    sugerida, dias, motivo = tasa_sugerida(prestamo, periodo.fecha_limite, fecha)
    normal, mora = prestamo.tasa_interes, tasa_mora_de(prestamo)
    previa = periodo.tasa_elegida or CERO

    def pendiente(tasa: Decimal) -> Decimal:
        return max(CERO, interes_mensual(prestamo, max(tasa, previa), periodo.base) - periodo.pagado)

    capital_otros = sum(
        (a.monto_capital for a in prestamo.abonos if excluir_abono_id is None or a.id != excluir_abono_id), CERO,
    )
    return AbonoVistaPrevia(
        numero_cuota=periodo.numero_cuota,
        fecha_limite=periodo.fecha_limite,
        fecha_pago=fecha,
        dias_retraso=dias,
        tasa_sugerida=sugerida,
        motivo=motivo,
        tasa_normal=normal,
        tasa_mora=mora,
        interes_tasa_normal=interes_mensual(prestamo, normal, periodo.base),
        interes_tasa_mora=interes_mensual(prestamo, mora, periodo.base),
        interes_pagado=periodo.pagado,
        pendiente_tasa_normal=pendiente(normal),
        pendiente_tasa_mora=pendiente(mora),
        tasa_elegida_previa=periodo.tasa_elegida,
        destino=periodo.destino,
        saldo_capital=max(CERO, prestamo.monto_prestado - capital_otros),
        cuotas_disponibles=[p.numero_cuota for p in periodos],
        cuotas=[
            CuotaDisponible(
                numero_cuota=p.numero_cuota, fecha_limite=p.fecha_limite, nueva=p.nueva,
                pagada=p.pagado > 0 and p.pendiente == 0,
            )
            for p in periodos
        ],
        cuota_nueva=next((p.numero_cuota for p in periodos if p.nueva), None),
        regla_interes=prestamo.regla_interes,
        capital_base=periodo.base,
        interes_socio=periodo.interes_socio if es_regla_reparto(prestamo) else None,
        interes_bien_comun=periodo.interes_bien_comun if es_regla_reparto(prestamo) else None,
    )


@router.post("/{prestamo_id}/abonos", response_model=AbonoPrestamoResponse, status_code=status.HTTP_201_CREATED, summary="Abonar a cuota de préstamo")
def registrar_abono_prestamo(
    prestamo_id: int,
    abono_in: AbonoPrestamoCreate,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db)
) -> AbonoPrestamo:
    """
    Registra el pago de una cuota de crédito:
    - Amortiza capital y reduce transaccionalmente el saldo pendiente.
    - Incrementa el conteo de cuotas pagadas.
    - Marca PAGADO cuando se cubren tanto el capital como los intereses.
    - Regla 7 %/10 %: guarda la tasa elegida, la fecha límite y los días de retraso.
    """
    prestamo = _prestamo_bloqueado(db, prestamo_id)

    validar_fecha_abono(abono_in.fecha_pago)
    recalcular_prestamo(db, prestamo)
    if prestamo.estado == EstadoPrestamo.PAGADO.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El préstamo ya se encuentra completamente cancelado",
        )

    extras = {}
    if es_regla_mora(prestamo):
        calculo = calcular_abono_mora(prestamo, abono_in)
        monto_capital, monto_interes, numero_cuota = calculo.monto_capital, calculo.monto_interes, calculo.numero_cuota
        extras = {
            "tasa_aplicada": calculo.tasa_aplicada if monto_interes > 0 else None,
            "fecha_limite": calculo.fecha_limite,
            "dias_retraso": calculo.dias_retraso,
        }
    else:
        if abono_in.monto_capital is not None:
            monto_interes = abono_in.monto_interes or Decimal("0.00")
            if monto_interes + abono_in.monto_capital != abono_in.monto_abonado:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="El capital y el interés deben sumar exactamente el monto abonado",
                )
            if abono_in.monto_capital > prestamo.saldo_pendiente:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="El capital abonado no puede superar el saldo pendiente",
                )

        # Calcular desglose capital vs interés si no viene desagregado
        if abono_in.monto_capital is not None:
            monto_capital = abono_in.monto_capital
            monto_interes = abono_in.monto_interes or Decimal("0.00")
        else:
            # Si no se desglosa, se amortiza hasta el tope del saldo de capital
            monto_capital = min(prestamo.saldo_pendiente, abono_in.monto_abonado)
            monto_interes = max(Decimal("0.00"), abono_in.monto_abonado - monto_capital)

        numero_cuota = abono_in.numero_cuota or (prestamo.cuotas_pagadas + 1)

    db_abono = AbonoPrestamo(
        prestamo_id=prestamo_id,
        monto_abonado=abono_in.monto_abonado,
        monto_capital=monto_capital,
        monto_interes=monto_interes,
        numero_cuota=numero_cuota,
        interes_bien_comun=parte_bien_comun(prestamo, monto_interes),
        **extras,
    )
    if abono_in.fecha_pago:
        db_abono.fecha_pago = fecha_a_datetime(abono_in.fecha_pago)
    db.add(db_abono)

    recalcular_prestamo(db, prestamo)

    tasa_txt = f" al {extras['tasa_aplicada']:g} %" if extras.get("tasa_aplicada") is not None else ""
    registrar_movimiento(
        db=db,
        modulo="Préstamos",
        tipo_accion="CREAR",
        descripcion=f"Abono de cuota #{db_abono.numero_cuota}{tasa_txt} por ${db_abono.monto_abonado:,.2f} al préstamo #{prestamo_id}",
        entidad_tipo="AbonoPrestamo",
        entidad_id=db_abono.id,
        datos_nuevos=db_abono,
        usuario=current_user,
        commit_now=True
    )

    return db_abono


@router.put("/{prestamo_id}/abonos/{abono_id}", response_model=AbonoPrestamoResponse, summary="Editar un abono de préstamo")
def editar_abono_prestamo(
    prestamo_id: int,
    abono_id: int,
    abono_in: AbonoPrestamoCreate,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db)
) -> AbonoPrestamo:
    """Corrige los valores de un abono y recalcula el saldo del préstamo."""
    prestamo = db.execute(select(Prestamo).where(Prestamo.id == prestamo_id).with_for_update()).scalar_one_or_none()
    abono = db.execute(
        select(AbonoPrestamo).where(
            AbonoPrestamo.id == abono_id,
            AbonoPrestamo.prestamo_id == prestamo_id,
        )
    ).scalar_one_or_none()

    if not prestamo or not abono:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Préstamo o abono no encontrado",
        )

    validar_fecha_abono(abono_in.fecha_pago)
    datos_previos = model_to_dict(abono)
    otros_abonos = [otro for otro in prestamo.abonos if otro.id != abono_id]
    capital_restante = prestamo.monto_prestado - sum(
        (otro.monto_capital for otro in otros_abonos), Decimal("0.00")
    )

    if es_regla_mora(prestamo):
        datos = abono_in.model_copy(update={
            "numero_cuota": abono_in.numero_cuota or abono.numero_cuota,
            "fecha_pago": abono_in.fecha_pago or fecha_local(abono.fecha_pago),
        })
        calculo = calcular_abono_mora(prestamo, datos, excluir_abono_id=abono_id, saldo_capital=capital_restante)
        abono.monto_abonado = abono_in.monto_abonado
        abono.monto_capital = calculo.monto_capital
        abono.monto_interes = calculo.monto_interes
        abono.numero_cuota = calculo.numero_cuota
        abono.tasa_aplicada = calculo.tasa_aplicada if calculo.monto_interes > 0 else None
        abono.fecha_limite = calculo.fecha_limite
        abono.dias_retraso = calculo.dias_retraso
        abono.interes_bien_comun = parte_bien_comun(prestamo, calculo.monto_interes)
    else:
        monto_interes = abono_in.monto_interes or Decimal("0.00")
        monto_capital = abono_in.monto_capital
        if monto_capital is None:
            monto_capital = min(capital_restante, abono_in.monto_abonado)
            monto_interes = abono_in.monto_abonado - monto_capital
        if monto_capital > capital_restante:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="El capital abonado supera el capital pendiente del préstamo",
            )

        abono.monto_abonado = abono_in.monto_abonado
        abono.monto_capital = monto_capital
        abono.monto_interes = monto_interes
        abono.numero_cuota = abono_in.numero_cuota or abono.numero_cuota
    if abono_in.fecha_pago:
        abono.fecha_pago = fecha_a_datetime(abono_in.fecha_pago)

    recalcular_prestamo(db, prestamo)
    registrar_movimiento(
        db=db, modulo="Préstamos", tipo_accion="EDITAR",
        descripcion=f"Abono #{abono.id} editado en préstamo #{prestamo_id}",
        entidad_tipo="AbonoPrestamo", entidad_id=abono.id,
        datos_previos=datos_previos, datos_nuevos=abono, usuario=current_user,
    )
    db.commit()
    db.refresh(abono)
    return abono


@router.get("", response_model=List[PrestamoResponse], summary="Listar préstamos")
def list_prestamos(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Session = Depends(get_db),
    socio_id: Optional[int] = Query(None, description="Filtrar por socio"),
    estado: Optional[EstadoPrestamo] = Query(None, description="PENDIENTE, PAGADO o EN_MORA"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500)
) -> List[Prestamo]:
    """Retorna listado de préstamos ordenados por fecha de desembolso descendente."""
    sincronizar_moras(db)
    query = select(Prestamo)

    if socio_id:
        query = query.where(Prestamo.socio_id == socio_id)
    if estado:
        query = query.where(Prestamo.estado == estado.value)

    query = query.order_by(Prestamo.fecha_prestamo.desc(), Prestamo.id.desc()).offset(skip).limit(limit)
    return db.execute(query).scalars().all()


@router.get("/consolidado/global", summary="Consolidado global de préstamos y cartera por socio (RF9)")
def get_consolidado_global_prestamos(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """
    Criterio RF9: Retorna el monto global prestado, el saldo pendiente consolidado y
    una lista detallada por socio con su saldo adeudado.
    """
    sincronizar_moras(db)
    # 1. Agregaciones globales
    stmt_global = select(
        func.coalesce(func.sum(Prestamo.monto_prestado), Decimal("0.00")),
        func.coalesce(func.sum(Prestamo.saldo_pendiente), Decimal("0.00")),
        func.count(Prestamo.id)
    )
    monto_global_prestado, saldo_global_pendiente, total_prestamos = db.execute(stmt_global).one()

    # Total préstamos que aún tienen saldo activo
    stmt_activos = select(func.count(Prestamo.id)).where(Prestamo.estado.notin_(ESTADOS_CERRADOS))
    total_activos = db.execute(stmt_activos).scalar_one()

    # 2. Desglose detallado por socio
    stmt_por_socio = (
        select(
            Socio.id,
            Socio.cedula,
            Socio.nombre,
            func.count(Prestamo.id).label("total_prestamos"),
            func.coalesce(func.sum(Prestamo.saldo_pendiente), Decimal("0.00")).label("saldo_pendiente_total")
        )
        .join(Prestamo, Prestamo.socio_id == Socio.id)
        .where(Prestamo.estado.notin_(ESTADOS_CERRADOS))
        .group_by(Socio.id, Socio.cedula, Socio.nombre)
        .order_by(func.sum(Prestamo.saldo_pendiente).desc())
    )
    filas = db.execute(stmt_por_socio).all()

    detalle_socios = [
        ResumenPrestamoSocio(
            socio_id=fila[0],
            cedula=fila[1],
            nombre=fila[2],
            total_prestamos=fila[3],
            saldo_pendiente_total=fila[4],
        )
        for fila in filas
    ]

    return {
        "monto_global_prestado": monto_global_prestado,
        "monto_global_saldo_pendiente": saldo_global_pendiente,
        "total_prestamos_historicos": total_prestamos,
        "total_prestamos_activos": total_activos,
        "socios_con_saldo_pendiente": len(detalle_socios),
        "detalle_por_socio": detalle_socios,
    }


@router.delete("/{prestamo_id}", status_code=status.HTTP_200_OK, summary="Eliminar un préstamo")
def delete_prestamo(
    prestamo_id: int,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db)
):
    """Elimina un préstamo y sus abonos asociados de forma permanente."""
    stmt = select(Prestamo).where(Prestamo.id == prestamo_id)
    prestamo = db.execute(stmt).scalar_one_or_none()

    if not prestamo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Préstamo con ID {prestamo_id} no encontrado",
        )

    total_abonado = sum((abono.monto_abonado for abono in prestamo.abonos), Decimal("0.00"))
    total_deuda = prestamo.monto_prestado + prestamo.total_intereses
    saldo_total = total_deuda - total_abonado
    if saldo_total > Decimal("0.00"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede eliminar el préstamo mientras tenga deuda pendiente",
        )

    socio_nombre = prestamo.socio.nombre if prestamo.socio else f"Socio #{prestamo.socio_id}"
    registrar_movimiento(
        db=db,
        modulo="Préstamos",
        tipo_accion="ELIMINAR",
        descripcion=f"Se eliminó el préstamo #{prestamo.id} de {socio_nombre} por ${prestamo.monto_prestado:,.2f}",
        entidad_tipo="Prestamo",
        entidad_id=prestamo.id,
        datos_previos=prestamo,
        usuario=current_user,
        commit_now=False
    )

    db.delete(prestamo)
    db.commit()
    return {"message": f"Préstamo {prestamo_id} eliminado exitosamente", "prestamo_id": prestamo_id}


@router.get("/{prestamo_id}", response_model=PrestamoResponse, summary="Detalle de préstamo con abonos")
def get_prestamo(
    prestamo_id: int,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Session = Depends(get_db)
) -> Prestamo:
    """Consulta la ficha completa de un préstamo y el desglose de sus abonos."""
    sincronizar_moras(db)
    stmt = select(Prestamo).where(Prestamo.id == prestamo_id)
    prestamo = db.execute(stmt).scalar_one_or_none()

    if not prestamo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Préstamo con ID {prestamo_id} no encontrado",
        )
    return prestamo
