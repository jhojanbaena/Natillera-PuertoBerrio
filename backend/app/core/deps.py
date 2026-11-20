"""Dependencias de Inyección para Autenticación y Autorización en FastAPI."""
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.usuario import Usuario

# Esquema de autenticación Bearer para Swagger UI y clientes HTTP
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)


def get_authenticated_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db)
) -> Usuario:
    """
    Decodifica el token JWT y recupera el usuario correspondiente desde la base de datos.
    Arroja HTTP 401 si el token es inválido o el usuario no existe.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales de autenticación inválidas o expiradas",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    username: str = payload.get("sub")
    # Los tokens del portal de socios nunca sirven para el sistema administrativo.
    if username is None or "aud" in payload:
        raise credentials_exception

    # Buscar usuario en la base de datos
    stmt = select(Usuario).where(Usuario.username == username)
    user = db.execute(stmt).scalar_one_or_none()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario se encuentra inactivo",
        )

    return user


def get_current_user(
    current_user: Annotated[Usuario, Depends(get_authenticated_user)]
) -> Usuario:
    """Usuario de los módulos de la natillera. El rol Desarrollador también tiene acceso a todo."""
    return current_user


def get_current_developer(
    current_user: Annotated[Usuario, Depends(get_authenticated_user)]
) -> Usuario:
    """Verifica que el usuario actual tenga el rol Desarrollador (el Administrador no lo tiene)."""
    if not current_user.is_developer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este apartado es exclusivo del rol Desarrollador",
        )
    return current_user


def get_current_active_admin(
    current_user: Annotated[Usuario, Depends(get_current_user)]
) -> Usuario:
    """Verifica privilegios de administrador. El rol Desarrollador también los tiene
    (puede ver y usar todo); el Administrador, en cambio, no accede al Panel."""
    if not (current_user.is_admin or current_user.is_developer):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no posee permisos de administrador requeridos",
        )
    return current_user
