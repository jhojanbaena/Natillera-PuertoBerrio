"""Portal de socios (/portal-socio): "Permitir vista a los socios".

- POST /portal-socio/login: usuario y contraseña son la cédula registrada (solo números).
- GET  /portal-socio/mi-hoja: la ficha de Total ahorrado del propio socio, la misma
  del botón Imprimir. El ID sale del token, nunca de la URL ni del cuerpo.

El token del socio tiene audiencia propia y no sirve en ninguna otra ruta. En
cada solicitud se vuelve a leer la configuración del Panel (rol Desarrollador):
si se desactiva el acceso o el socio queda fuera del rango, deja de entrar.
Nada aquí escribe en la base, salvo el contador de intentos de login y el
recálculo de moras que también hace la hoja del administrador.
"""
import hmac
import re
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.deps import oauth2_scheme
from app.core.login_limit import check_login_limit
from app.core.security import create_socio_token, decode_socio_token
from app.core.vista_socios import (
    buscar_socio_por_cedula, get_db_activo, huella_cedula, leer_config, modo_vigente,
    socio_puede_entrar, solo_digitos, version_vigente,
)
from app.models.socio import Socio
from app.models.vista_socios import MODO_DESACTIVADO
from app.routers.socios import datos_hoja_ahorro
from app.schemas.usuario import Token
from app.schemas.vista_socios import SocioLogin

router = APIRouter(prefix="/portal-socio", tags=["Portal de socios"])
CEDULA_VALIDA = re.compile(r"^\d{5,20}$")


def _no_autorizado(detalle: str = "Cédula incorrecta o sin acceso a la vista de socios") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detalle, headers={"WWW-Authenticate": "Bearer"})


def _acceso_desactivado() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La vista para los socios no está habilitada en este momento")


@router.post("/login", response_model=Token, summary="Inicio de sesión del socio (cédula / cédula)")
def login_socio(credenciales: SocioLogin, db: Session = Depends(get_db_activo)) -> Token:
    usuario = credenciales.username.strip()
    # El límite se cuenta por cédula escrita (se guarda solo su hash SHA-256).
    check_login_limit(db, "socio:" + usuario)
    if not CEDULA_VALIDA.match(usuario) or not hmac.compare_digest(
        usuario.encode("utf-8"), credenciales.password.strip().encode("utf-8")
    ):
        raise _no_autorizado()
    config = leer_config(db)
    if modo_vigente(config) == MODO_DESACTIVADO:
        raise _acceso_desactivado()
    socio = buscar_socio_por_cedula(db, usuario)
    if socio is None or not socio_puede_entrar(config, socio):
        raise _no_autorizado()
    token = create_socio_token(socio.id, huella_cedula(usuario), version_vigente(config))
    return Token(access_token=token, token_type="bearer")


def get_current_socio(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db_activo),
) -> Socio:
    """Socio del token, comprobando en cada solicitud la configuración vigente del Panel."""
    payload = decode_socio_token(token)
    if payload is None or not isinstance(payload.get("sid"), int) or not isinstance(payload.get("ver"), int):
        raise _no_autorizado("Tu sesión terminó; vuelve a ingresar")
    config = leer_config(db)
    if modo_vigente(config) == MODO_DESACTIVADO or payload["ver"] != version_vigente(config):
        raise _no_autorizado("La vista para los socios fue deshabilitada")
    socio = db.get(Socio, payload["sid"])
    # La huella evita que el token sirva para otra persona si el ID cambia de dueño.
    if socio is None or not hmac.compare_digest(huella_cedula(solo_digitos(socio.cedula)), str(payload.get("ced", ""))):
        raise _no_autorizado("Tu sesión terminó; vuelve a ingresar")
    if not socio_puede_entrar(config, socio):
        raise _no_autorizado("Tu cuenta ya no tiene acceso a la vista de socios")
    return socio


@router.get("/mi-hoja", summary="Ficha de Total ahorrado del socio autenticado")
def mi_hoja(
    socio: Annotated[Socio, Depends(get_current_socio)],
    db: Session = Depends(get_db_activo),
) -> dict:
    return datos_hoja_ahorro(db, socio)
