"""Router de Estadísticas de los movimientos económicos (/estadisticas).

- Consultar: calcula las gráficas con los datos reales del año consultado.
- Guardar: guarda una fotografía (filtros + resultados) que ya no cambia.
"""
from datetime import date
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_active_admin, get_current_user
from app.models.estadistica import EstadisticaGuardada
from app.models.usuario import Usuario
from app.schemas.estadistica import (
    EstadisticaGuardadaResponse, EstadisticaGuardadaResumen, EstadisticaGuardar, FiltrosEstadistica,
)
from app.services.estadisticas_service import TIPOS_MOVIMIENTO, calcular_estadistica, listar_eventos

router = APIRouter(prefix="/estadisticas", tags=["Estadísticas"])


def _filtros(
    modo: str = Query("todo"),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    evento: Optional[str] = Query(None, max_length=30),
    tipos: Optional[str] = Query(None, max_length=500, description="Tipos separados por coma"),
) -> FiltrosEstadistica:
    try:
        return FiltrosEstadistica(
            modo=modo, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, evento=evento or None,
            tipos=[t for t in (tipos or "").split(",") if t],
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False, include_context=False, include_input=False))


@router.get("/opciones", summary="Tipos de movimiento y eventos disponibles para filtrar")
def get_opciones(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> dict:
    return {
        "tipos": [{"tipo": t, "etiqueta": e, "naturaleza": n} for t, (e, n) in TIPOS_MOVIMIENTO.items()],
        "eventos": listar_eventos(db),
    }


@router.get("", summary="Estadística de los movimientos según los filtros")
def get_estadistica(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    filtros: Annotated[FiltrosEstadistica, Depends(_filtros)],
    db: Session = Depends(get_db),
) -> dict:
    return calcular_estadistica(db, filtros.model_dump())


def _resumen(e: EstadisticaGuardada) -> dict:
    return {
        "id": e.id, "nombre": e.nombre, "anio": e.anio, "filtros": e.filtros,
        "totales": (e.resultados or {}).get("totales", {}), "usuario_nombre": e.usuario_nombre,
        "created_at": e.created_at,
    }


@router.get("/guardadas", response_model=List[EstadisticaGuardadaResumen], summary="Estadísticas guardadas")
def list_guardadas(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> list:
    filas = db.execute(select(EstadisticaGuardada).order_by(EstadisticaGuardada.created_at.desc(),
                                                            EstadisticaGuardada.id.desc())).scalars().all()
    return [_resumen(e) for e in filas]


@router.get("/guardadas/{estadistica_id}", response_model=EstadisticaGuardadaResponse, summary="Estadística guardada")
def get_guardada(
    estadistica_id: int,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> dict:
    e = db.get(EstadisticaGuardada, estadistica_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Estadística no encontrada")
    return {**_resumen(e), "resultados": e.resultados}


@router.post("/guardadas", response_model=EstadisticaGuardadaResponse, status_code=status.HTTP_201_CREATED,
             summary="Guardar la estadística con sus resultados de este momento")
def create_guardada(
    datos: EstadisticaGuardar,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db),
) -> dict:
    # Los resultados se calculan en el servidor (no se aceptan cifras del cliente).
    resultados = calcular_estadistica(db, datos.filtros.model_dump())
    e = EstadisticaGuardada(
        nombre=datos.nombre,
        anio=resultados["anio"],
        filtros=datos.filtros.model_dump(mode="json"),
        resultados=resultados,
        usuario_nombre=current_user.nombre_completo or current_user.username,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return {**_resumen(e), "resultados": e.resultados}


@router.delete("/guardadas/{estadistica_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Eliminar una estadística guardada")
def delete_guardada(
    estadistica_id: int,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db),
) -> None:
    e = db.get(EstadisticaGuardada, estadistica_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Estadística no encontrada")
    db.delete(e)
    db.commit()
