"""Router de Gastos Generales (/gastos-generales).

Los gastos de un año se reparten en partes iguales entre los socios activos y se
descuentan de su liquidación de ese año (ver FinanzasService.calcular_liquidacion_anual).
"""
from decimal import Decimal
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.periodos import anio_del_periodo
from app.core.database import get_db
from app.core.deps import get_current_active_admin, get_current_user
from app.models.gastos import GastoGeneral
from app.models.socio import Socio
from app.models.usuario import Usuario
from app.schemas.gastos import (
    GastoGeneralCreate, GastoGeneralResponse, GastoGeneralUpdate, GastosGeneralesResumen,
)
from app.services.finanzas_service import FinanzasService
from app.services.historial_service import model_to_dict, registrar_movimiento

router = APIRouter(prefix="/gastos-generales", tags=["Gastos Generales"])
CERO = Decimal("0.00")


def _gasto(db: Session, gasto_id: int) -> GastoGeneral:
    gasto = db.get(GastoGeneral, gasto_id)
    if gasto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Gasto con ID {gasto_id} no encontrado")
    return gasto


@router.get("", response_model=GastosGeneralesResumen, summary="Gastos generales del año y valor por socio activo")
def resumen_gastos(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Session = Depends(get_db),
    anio: Optional[int] = Query(None, ge=2000, le=2100, description="Año de liquidación; por defecto el actual"),
) -> GastosGeneralesResumen:
    anio = anio or anio_del_periodo(db)
    gastos = db.execute(
        select(GastoGeneral).where(GastoGeneral.anio == anio).order_by(GastoGeneral.id.asc())
    ).scalars().all()
    total = sum((g.monto for g in gastos), CERO)
    socios_activos = db.execute(select(func.count(Socio.id)).where(Socio.is_active.is_(True))).scalar_one()
    # Sin socios activos no se divide (evita división entre cero).
    por_socio = (total / socios_activos).quantize(Decimal("0.01")) if socios_activos else CERO
    anios = set(FinanzasService.anios_con_movimientos(db))
    anios.update(db.execute(select(GastoGeneral.anio).distinct()).scalars().all())
    anios.add(anio)
    return GastosGeneralesResumen(
        anio=anio,
        anios_disponibles=sorted(anios, reverse=True),
        gastos=gastos,
        total_gastos=total,
        socios_activos=socios_activos,
        gasto_por_socio=por_socio,
    )


@router.post("", response_model=GastoGeneralResponse, status_code=status.HTTP_201_CREATED, summary="Agregar un gasto general")
def crear_gasto(
    gasto_in: GastoGeneralCreate,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db),
) -> GastoGeneral:
    gasto = GastoGeneral(
        anio=gasto_in.anio or anio_del_periodo(db),
        descripcion=gasto_in.descripcion,
        monto=gasto_in.monto,
    )
    db.add(gasto)
    db.flush()
    registrar_movimiento(
        db=db, modulo="Gastos Generales", tipo_accion="CREAR",
        descripcion=f"Gasto general '{gasto.descripcion}' ({gasto.anio}) por ${gasto.monto:,.2f}",
        entidad_tipo="GastoGeneral", entidad_id=gasto.id, datos_nuevos=gasto, usuario=current_user,
    )
    db.commit()
    db.refresh(gasto)
    return gasto


@router.put("/{gasto_id}", response_model=GastoGeneralResponse, summary="Editar un gasto general")
def editar_gasto(
    gasto_id: int,
    gasto_in: GastoGeneralUpdate,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db),
) -> GastoGeneral:
    gasto = _gasto(db, gasto_id)
    previos = model_to_dict(gasto)
    gasto.descripcion = gasto_in.descripcion
    gasto.monto = gasto_in.monto
    db.flush()
    registrar_movimiento(
        db=db, modulo="Gastos Generales", tipo_accion="EDITAR",
        descripcion=f"Gasto general #{gasto.id} editado: '{gasto.descripcion}' por ${gasto.monto:,.2f}",
        entidad_tipo="GastoGeneral", entidad_id=gasto.id, datos_previos=previos, datos_nuevos=gasto,
        usuario=current_user,
    )
    db.commit()
    db.refresh(gasto)
    return gasto


@router.delete("/{gasto_id}", summary="Eliminar un gasto general")
def eliminar_gasto(
    gasto_id: int,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db),
):
    gasto = _gasto(db, gasto_id)
    registrar_movimiento(
        db=db, modulo="Gastos Generales", tipo_accion="ELIMINAR",
        descripcion=f"Gasto general '{gasto.descripcion}' ({gasto.anio}) por ${gasto.monto:,.2f} eliminado",
        entidad_tipo="GastoGeneral", entidad_id=gasto.id, datos_previos=gasto, usuario=current_user,
    )
    db.delete(gasto)
    db.commit()
    return {"message": "Gasto eliminado", "gasto_id": gasto_id}
