"""Router del Panel del Desarrollador (/panel).

Exclusivo del rol Desarrollador: el Administrador y los demás usuarios reciben
HTTP 403.

Funcionalidades:
- Permitir vista a los socios: todos, un rango de ID o desactivado.
"""
from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.deps import get_current_developer
from app.core.vista_socios import (
    CONFIG_ID, cedula_bloqueada, get_db_activo, id_autorizado, leer_config, modo_vigente, solo_digitos,
)
from app.models.socio import Socio
from app.models.usuario import Usuario
from app.models.vista_socios import ConfigVistaSocios, MODO_DESACTIVADO
from app.schemas.vista_socios import VistaSociosResponse, VistaSociosUpdate

router = APIRouter(prefix="/panel", tags=["Panel del Desarrollador"])


@router.get("", summary="Estado del Panel del Desarrollador")
def get_panel(current_user: Annotated[Usuario, Depends(get_current_developer)]) -> dict:
    return {"panel": "desarrollador", "usuario": current_user.username, "funcionalidades": ["vista-socios"]}


def _respuesta(db: Session, config) -> VistaSociosResponse:
    # db es del año activo: los socios del portal siempre son los de ese año.
    con_acceso = bloqueados = 0
    for socio_id, cedula in db.execute(select(Socio.id, Socio.cedula).where(Socio.is_active.is_(True))).all():
        if not id_autorizado(config, socio_id):
            continue
        if cedula_bloqueada(solo_digitos(cedula)):
            bloqueados += 1
        else:
            con_acceso += 1
    return VistaSociosResponse(
        modo=modo_vigente(config),
        id_inicio=config.id_inicio if config else None,
        id_fin=config.id_fin if config else None,
        actualizado_por=config.usuario_nombre if config else None,
        actualizado_en=config.updated_at if config else None,
        socios_con_acceso=con_acceso,
        socios_bloqueados=bloqueados,
    )


@router.get("/vista-socios", response_model=VistaSociosResponse, summary="Configuración de la vista a los socios")
def get_vista_socios(
    current_user: Annotated[Usuario, Depends(get_current_developer)],
    db: Session = Depends(get_db_activo),
) -> VistaSociosResponse:
    return _respuesta(db, leer_config(db))


@router.put("/vista-socios", response_model=VistaSociosResponse, summary="Guardar la configuración de la vista a los socios")
def put_vista_socios(
    datos: VistaSociosUpdate,
    current_user: Annotated[Usuario, Depends(get_current_developer)],
    db: Session = Depends(get_db_activo),
) -> VistaSociosResponse:
    config = leer_config(db, bloquear=True)
    if config is None:
        config = ConfigVistaSocios(id=CONFIG_ID, modo=MODO_DESACTIVADO, version=1)
        db.add(config)
    # Quitar el acceso cierra las sesiones abiertas: los tokens llevan la versión.
    if datos.modo == MODO_DESACTIVADO and config.modo != MODO_DESACTIVADO:
        config.version = (config.version or 1) + 1
    config.modo = datos.modo
    config.id_inicio = datos.id_inicio
    config.id_fin = datos.id_fin
    config.usuario_nombre = current_user.nombre_completo or current_user.username
    db.commit()
    db.refresh(config)
    return _respuesta(db, config)
