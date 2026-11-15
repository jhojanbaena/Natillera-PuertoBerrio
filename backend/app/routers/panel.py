"""Router del Panel del Desarrollador (/panel).

Exclusivo del rol Desarrollador: el Administrador y los demás usuarios reciben
HTTP 403. Por ahora no tiene funcionalidades; aquí se irán agregando.
"""
from typing import Annotated
from fastapi import APIRouter, Depends
from app.core.deps import get_current_developer
from app.models.usuario import Usuario

router = APIRouter(prefix="/panel", tags=["Panel del Desarrollador"])


@router.get("", summary="Estado del Panel del Desarrollador")
def get_panel(current_user: Annotated[Usuario, Depends(get_current_developer)]) -> dict:
    return {"panel": "desarrollador", "usuario": current_user.username, "funcionalidades": []}
