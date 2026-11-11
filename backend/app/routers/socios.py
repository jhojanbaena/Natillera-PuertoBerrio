"""Router para la Gestión Integral de Socios (/socios).
Cumple con los criterios RF2-RF3 (CRUD completo, listado ordenado y perfil financiero detallado).
"""
from decimal import Decimal
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, func
from app.core.database import get_db
from app.core.deps import get_current_active_admin, get_current_user
from app.models.usuario import Usuario
from app.models.socio import Socio
from app.models.finanzas import FinanzaSocio, TipoMovimientoFinanciero
from app.models.prestamo import Prestamo, EstadoPrestamo
from app.services.prestamos_service import fecha_a_datetime, sincronizar_moras, validar_fecha_registro
from app.schemas.socio import SocioCreate, SocioUpdate, SocioResponse, SocioDetailResponse
from app.schemas.finanzas import FinanzaMovimientoCreate, FinanzaResponse, MultaEstadoItem, MultaUpdate
from app.services.historial_service import registrar_movimiento, model_to_dict
from app.services.socio_service import cambiar_id_socio

router = APIRouter(prefix="/socios", tags=["Socios"])


def estado_multas(movimientos) -> List[MultaEstadoItem]:
    """Estado de pago de cada multa del socio.

    Un PAGO_MULTA con `multa_id` salda esa multa. Los pagos antiguos sin multa
    asociada se aplican a las multas restantes de la más antigua a la más reciente,
    de modo que lo ya pagado no vuelva a aparecer como pendiente.
    """
    multas = sorted(
        (m for m in movimientos if m.tipo_movimiento == TipoMovimientoFinanciero.MULTA.value),
        key=lambda m: (m.fecha, m.id),
    )
    ids_multas = {m.id for m in multas}
    pagos = [m for m in movimientos if m.tipo_movimiento == TipoMovimientoFinanciero.PAGO_MULTA.value]
    vinculados = {p.multa_id: p for p in pagos if p.multa_id in ids_multas}
    saldo_sin_vincular = sum(
        (p.monto for p in pagos if p.multa_id not in ids_multas), Decimal("0.00")
    )

    resultado = []
    for multa in multas:
        pago = vinculados.get(multa.id)
        pagada = pago is not None
        if not pagada and saldo_sin_vincular >= multa.monto:
            saldo_sin_vincular -= multa.monto
            pagada = True
        resultado.append(MultaEstadoItem(
            id=multa.id,
            monto=multa.monto,
            descripcion=multa.descripcion,
            fecha=multa.fecha,
            pagada=pagada,
            pago_id=pago.id if pago else None,
            fecha_pago=pago.fecha if pago else None,
        ))
    return resultado


@router.post("", response_model=SocioResponse, status_code=status.HTTP_201_CREATED, summary="Registrar un nuevo socio")
def create_socio(
    socio_in: SocioCreate,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db)
) -> Socio:
    """
    Crea un nuevo socio en el fondo.
    Valida obligatoriamente: Cédula única, nombre, teléfono, residencia y aporte mensual pactado.
    """
    stmt = select(Socio).where(Socio.cedula == socio_in.cedula.strip())
    existing_socio = db.execute(stmt).scalar_one_or_none()

    if existing_socio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ya existe un socio registrado con la cédula {socio_in.cedula}",
        )

    if socio_in.id is not None:
        existing_id = db.execute(select(Socio).where(Socio.id == socio_in.id)).scalar_one_or_none()
        if existing_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ya existe un socio registrado con el ID {socio_in.id}",
            )

    db_socio = Socio(
        id=socio_in.id,
        cedula=socio_in.cedula.strip(),
        nombre=socio_in.nombre.strip(),
        telefono=socio_in.telefono.strip(),
        residencia=socio_in.residencia.strip(),
        aporte_mensual=socio_in.aporte_mensual,
        is_active=True,
    )
    db.add(db_socio)
    db.flush()
    db.refresh(db_socio)

    registrar_movimiento(
        db=db,
        modulo="Socios",
        tipo_accion="CREAR",
        descripcion=f"Socio registrado: {db_socio.nombre} (C.C. {db_socio.cedula})",
        entidad_tipo="Socio",
        entidad_id=db_socio.id,
        datos_nuevos=db_socio,
        usuario=current_user,
        commit_now=True
    )

    return db_socio


@router.get("", response_model=List[SocioResponse], summary="Listado general de socios")
def list_socios(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0, description="Paginación: registros a omitir"),
    limit: int = Query(100, ge=1, le=500, description="Paginación: límite de registros"),
    q: Optional[str] = Query(None, description="Búsqueda por nombre o cédula"),
    solo_activos: bool = Query(True, description="Filtrar únicamente socios activos"),
    ordenar_por: str = Query("nombre", pattern="^(nombre|cedula|id)$", description="Campo de ordenamiento")
) -> List[Socio]:
    """
    Retorna el listado general de socios ordenado alfabéticamente por nombre (o id/cédula).
    Permite búsqueda por texto y paginación.
    """
    query = select(Socio)

    if solo_activos:
        query = query.where(Socio.is_active.is_(True))

    if q:
        search_pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                Socio.nombre.ilike(search_pattern),
                Socio.cedula.ilike(search_pattern)
            )
        )

    if ordenar_por == "id":
        query = query.order_by(Socio.id.asc())
    elif ordenar_por == "cedula":
        query = query.order_by(Socio.cedula.asc())
    else:
        query = query.order_by(Socio.nombre.asc())

    query = query.offset(skip).limit(limit)
    socios = db.execute(query).scalars().all()
    return socios


@router.get("/{socio_id}", response_model=SocioResponse, summary="Obtener información básica de un socio")
def get_socio(
    socio_id: int,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Session = Depends(get_db)
) -> Socio:
    """Consulta los datos básicos de un socio por su ID."""
    stmt = select(Socio).where(Socio.id == socio_id)
    socio = db.execute(stmt).scalar_one_or_none()

    if not socio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Socio con ID {socio_id} no encontrado",
        )
    return socio


@router.put("/{socio_id}", response_model=SocioResponse, summary="Actualizar datos de un socio")
def update_socio(
    socio_id: int,
    socio_in: SocioUpdate,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db)
) -> Socio:
    """Actualiza la información personal, cédula, ID o cuota mensual de un socio."""
    stmt = select(Socio).where(Socio.id == socio_id).with_for_update()
    socio = db.execute(stmt).scalar_one_or_none()

    if not socio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Socio con ID {socio_id} no encontrado",
        )

    datos_previos = model_to_dict(socio)

    # Validar que la cédula no esté en uso por otro socio
    if socio_in.cedula and socio_in.cedula.strip() != socio.cedula:
        cedula_check = select(Socio).where(
            Socio.cedula == socio_in.cedula.strip(),
            Socio.id != socio_id
        )
        if db.execute(cedula_check).scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La cédula {socio_in.cedula} ya está asignada a otro miembro",
            )
        socio.cedula = socio_in.cedula.strip()

    if socio_in.nombre is not None:
        socio.nombre = socio_in.nombre.strip()
    if socio_in.telefono is not None:
        socio.telefono = socio_in.telefono.strip()
    if socio_in.residencia is not None:
        socio.residencia = socio_in.residencia.strip()
    if socio_in.aporte_mensual is not None:
        socio.aporte_mensual = socio_in.aporte_mensual
    if socio_in.is_active is not None:
        socio.is_active = socio_in.is_active

    db.flush()
    db.refresh(socio)

    # Cambio de ID: mueve también sus aportes, multas, préstamos e historial.
    descripcion = f"Datos actualizados del socio {socio.nombre} (C.C. {socio.cedula})"
    if socio_in.id is not None and socio_in.id != socio_id:
        socio = cambiar_id_socio(db, socio, socio_in.id)
        descripcion += f" — ID cambiado de {socio_id} a {socio.id}"

    registrar_movimiento(
        db=db,
        modulo="Socios",
        tipo_accion="EDITAR",
        descripcion=descripcion,
        entidad_tipo="Socio",
        entidad_id=socio.id,
        datos_previos=datos_previos,
        datos_nuevos=socio,
        usuario=current_user,
        commit_now=True
    )

    return socio


@router.delete("/{socio_id}", summary="Eliminar o desactivar un socio")
def delete_socio(
    socio_id: int,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    hard_delete: bool = Query(False, description="True para borrado físico permanente, False para inactivación"),
    db: Session = Depends(get_db)
):
    """
    Desactiva (soft-delete por defecto) o borra permanentemente un socio y su registro en cascada.
    """
    stmt = select(Socio).where(Socio.id == socio_id)
    socio = db.execute(stmt).scalar_one_or_none()

    if not socio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Socio con ID {socio_id} no encontrado",
        )

    # Un socio con dinero ahorrado (aportes menos retiros) no se puede eliminar ni desactivar.
    totales = dict(db.execute(select(
        FinanzaSocio.tipo_movimiento, func.sum(FinanzaSocio.monto)
    ).where(FinanzaSocio.socio_id == socio_id).group_by(FinanzaSocio.tipo_movimiento)).all())
    ahorro = (totales.get(TipoMovimientoFinanciero.APORTE.value) or Decimal("0.00")) - (
        totales.get(TipoMovimientoFinanciero.RETIRO_AHORRO.value) or Decimal("0.00")
    )
    if ahorro > 0:
        ahorro_texto = f"{ahorro:,.0f}".replace(",", ".")  # formato colombiano: $800.000
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"No se puede eliminar a {socio.nombre}: tiene ${ahorro_texto} ahorrados. "
                "Primero se debe devolver o retirar su ahorro."
            ),
        )

    if hard_delete:
        registrar_movimiento(
            db=db,
            modulo="Socios",
            tipo_accion="ELIMINAR",
            descripcion=f"Se eliminó permanentemente al socio {socio.nombre} (C.C. {socio.cedula})",
            entidad_tipo="Socio",
            entidad_id=socio.id,
            datos_previos=socio,
            usuario=current_user,
            commit_now=False
        )
        db.delete(socio)
        db.commit()
        return {"message": f"Socio {socio_id} eliminado permanentemente", "socio_id": socio_id}
    else:
        datos_previos = model_to_dict(socio)
        socio.is_active = False
        db.flush()
        registrar_movimiento(
            db=db,
            modulo="Socios",
            tipo_accion="EDITAR",
            descripcion=f"Se desactivó al socio {socio.nombre} (C.C. {socio.cedula})",
            entidad_tipo="Socio",
            entidad_id=socio.id,
            datos_previos=datos_previos,
            datos_nuevos=socio,
            usuario=current_user,
            commit_now=True
        )
        return {"message": f"Socio {socio_id} desactivado exitosamente", "socio_id": socio_id}


@router.get("/{socio_id}/perfil", response_model=SocioDetailResponse, summary="Perfil financiero detallado del socio")
def get_socio_perfil(
    socio_id: int,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Session = Depends(get_db)
) -> SocioDetailResponse:
    """
    Genera el estado de cuenta y perfil financiero consolidado del socio:
    - Dinero ahorrado (Aportes netos).
    - Multas generadas vs pagadas y saldo pendiente por multas.
    - Estado y saldo de créditos o préstamos activos.
    - Historial completo de movimientos transaccionales.
    """
    stmt = select(Socio).where(Socio.id == socio_id)
    socio = db.execute(stmt).scalar_one_or_none()

    if not socio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Socio con ID {socio_id} no encontrado",
        )

    # 1. Historial de transacciones
    stmt_finanzas = select(FinanzaSocio).where(FinanzaSocio.socio_id == socio_id).order_by(FinanzaSocio.fecha.desc())
    historial_finanzas = db.execute(stmt_finanzas).scalars().all()

    total_aportes = Decimal("0.00")
    total_retiros = Decimal("0.00")
    total_multas = Decimal("0.00")
    total_multas_pagadas = Decimal("0.00")

    for f in historial_finanzas:
        if f.tipo_movimiento == TipoMovimientoFinanciero.APORTE.value:
            total_aportes += f.monto
        elif f.tipo_movimiento == TipoMovimientoFinanciero.RETIRO_AHORRO.value:
            total_retiros += f.monto
        elif f.tipo_movimiento == TipoMovimientoFinanciero.MULTA.value:
            total_multas += f.monto
        elif f.tipo_movimiento == TipoMovimientoFinanciero.PAGO_MULTA.value:
            total_multas_pagadas += f.monto

    total_ahorrado = max(Decimal("0.00"), total_aportes - total_retiros)
    total_multas_pendientes = max(Decimal("0.00"), total_multas - total_multas_pagadas)

    # 2. Préstamos del socio
    sincronizar_moras(db)
    stmt_prestamos = select(Prestamo).where(Prestamo.socio_id == socio_id).order_by(Prestamo.fecha_prestamo.desc())
    prestamos = db.execute(stmt_prestamos).scalars().all()

    total_prestamos_activos = sum(1 for p in prestamos if p.estado != EstadoPrestamo.PAGADO.value)
    saldo_prestamos_pendiente = sum(p.saldo_pendiente for p in prestamos if p.estado != EstadoPrestamo.PAGADO.value)

    return SocioDetailResponse(
        id=socio.id,
        cedula=socio.cedula,
        nombre=socio.nombre,
        telefono=socio.telefono,
        residencia=socio.residencia,
        aporte_mensual=socio.aporte_mensual,
        is_active=socio.is_active,
        created_at=socio.created_at,
        total_ahorrado=total_ahorrado,
        total_multas_pendientes=total_multas_pendientes,
        total_multas_pagadas=total_multas_pagadas,
        total_prestamos_activos=total_prestamos_activos,
        saldo_prestamos_pendiente=saldo_prestamos_pendiente,
        historial_finanzas=historial_finanzas,
        multas=estado_multas(historial_finanzas),
        prestamos=prestamos,
    )


@router.post("/{socio_id}/movimientos", response_model=FinanzaResponse, status_code=status.HTTP_201_CREATED, summary="Registrar movimiento financiero a socio (Aporte, Multa, Pago)")
def create_socio_movimiento(
    socio_id: int,
    movimiento_in: FinanzaMovimientoCreate,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db)
) -> FinanzaSocio:
    """
    Registra directamente un aporte, multa o pago de multa para el socio indicado.
    Si se indica `fecha`, el movimiento cuenta para ese día (y su año de liquidación).
    """
    validar_fecha_registro(movimiento_in.fecha)
    # Serializar movimientos del mismo socio antes de consultar fondos disponibles.
    stmt = select(Socio).where(Socio.id == socio_id).with_for_update()
    socio = db.execute(stmt).scalar_one_or_none()

    if not socio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Socio con ID {socio_id} no encontrado",
        )

    if movimiento_in.tipo_movimiento == TipoMovimientoFinanciero.RETIRO_AHORRO:
        totales = dict(db.execute(select(
            FinanzaSocio.tipo_movimiento, func.sum(FinanzaSocio.monto)
        ).where(FinanzaSocio.socio_id == socio_id).group_by(FinanzaSocio.tipo_movimiento)).all())
        disponible = totales.get("APORTE", Decimal("0.00")) - totales.get("RETIRO_AHORRO", Decimal("0.00"))
        if movimiento_in.monto > disponible:
            raise HTTPException(status_code=422, detail="El retiro no puede superar el ahorro disponible")

    # Aporte mensual: un solo registro por socio y mes.
    if movimiento_in.periodo is not None:
        if movimiento_in.tipo_movimiento != TipoMovimientoFinanciero.APORTE:
            raise HTTPException(status_code=422, detail="El mes solo aplica a aportes")
        ya_registrado = db.execute(select(FinanzaSocio.id).where(
            FinanzaSocio.socio_id == socio_id,
            FinanzaSocio.tipo_movimiento == TipoMovimientoFinanciero.APORTE.value,
            FinanzaSocio.periodo == movimiento_in.periodo,
        )).first()
        if ya_registrado:
            raise HTTPException(status_code=409, detail="El aporte de ese mes ya está registrado como pagado")

    # Pago de una multa concreta: debe existir, ser del socio, estar pendiente y pagarse completa.
    if movimiento_in.multa_id is not None:
        if movimiento_in.tipo_movimiento != TipoMovimientoFinanciero.PAGO_MULTA:
            raise HTTPException(status_code=422, detail="La multa solo aplica a pagos de multa")
        movimientos = db.execute(select(FinanzaSocio).where(FinanzaSocio.socio_id == socio_id)).scalars().all()
        multa = next((m for m in estado_multas(movimientos) if m.id == movimiento_in.multa_id), None)
        if multa is None:
            raise HTTPException(status_code=404, detail="La multa no existe para este socio")
        if multa.pagada:
            raise HTTPException(status_code=409, detail="Esta multa ya está pagada")
        if movimiento_in.monto != multa.monto:
            raise HTTPException(status_code=422, detail="El pago debe ser igual al valor de la multa")

    db_movimiento = FinanzaSocio(
        socio_id=socio_id,
        tipo_movimiento=movimiento_in.tipo_movimiento.value,
        monto=movimiento_in.monto,
        descripcion=movimiento_in.descripcion,
        periodo=movimiento_in.periodo,
        multa_id=movimiento_in.multa_id,
    )
    if movimiento_in.fecha:
        db_movimiento.fecha = fecha_a_datetime(movimiento_in.fecha)
    db.add(db_movimiento)
    db.flush()
    db.refresh(db_movimiento)

    registrar_movimiento(
        db=db,
        modulo="Finanzas",
        tipo_accion="CREAR",
        descripcion=f"Movimiento '{db_movimiento.tipo_movimiento}' por ${db_movimiento.monto:,.2f} registrado para socio {socio.nombre}",
        entidad_tipo="FinanzaSocio",
        entidad_id=db_movimiento.id,
        datos_nuevos=db_movimiento,
        usuario=current_user,
        commit_now=True
    )

    return db_movimiento


@router.put("/{socio_id}/multas/{multa_id}", response_model=FinanzaResponse, summary="Editar una multa pendiente")
def update_socio_multa(
    socio_id: int,
    multa_id: int,
    multa_in: MultaUpdate,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db)
) -> FinanzaSocio:
    """Modifica concepto o valor de una multa que aún no se ha pagado."""
    socio = db.execute(select(Socio).where(Socio.id == socio_id).with_for_update()).scalar_one_or_none()
    if not socio:
        raise HTTPException(status_code=404, detail=f"Socio con ID {socio_id} no encontrado")

    movimientos = db.execute(select(FinanzaSocio).where(FinanzaSocio.socio_id == socio_id)).scalars().all()
    multa = next((m for m in movimientos
                  if m.id == multa_id and m.tipo_movimiento == TipoMovimientoFinanciero.MULTA.value), None)
    if multa is None:
        raise HTTPException(status_code=404, detail="La multa no existe para este socio")
    if any(m.id == multa_id and m.pagada for m in estado_multas(movimientos)):
        raise HTTPException(status_code=409, detail="No se puede modificar una multa ya pagada")

    datos_previos = model_to_dict(multa)
    if multa_in.monto is not None:
        multa.monto = multa_in.monto
    if multa_in.descripcion is not None:
        multa.descripcion = multa_in.descripcion.strip() or multa.descripcion
    db.flush()
    db.refresh(multa)

    registrar_movimiento(
        db=db,
        modulo="Finanzas",
        tipo_accion="EDITAR",
        descripcion=f"Multa #{multa.id} modificada para socio {socio.nombre} (${multa.monto:,.2f})",
        entidad_tipo="FinanzaSocio",
        entidad_id=multa.id,
        datos_previos=datos_previos,
        datos_nuevos=multa,
        usuario=current_user,
        commit_now=True
    )
    return multa
