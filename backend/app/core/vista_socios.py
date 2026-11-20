"""Reglas de "Permitir vista a los socios": configuración vigente, cédulas y acceso.

La contraseña del socio es su cédula registrada, que ya está guardada como dato
del socio. No se guarda ninguna contraseña aparte: la cédula escrita se compara
con la registrada en tiempo constante (hmac.compare_digest). El token solo lleva
una huella HMAC de la cédula, nunca la cédula.
"""
import hashlib
import hmac
import re
from typing import Optional

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.periodos import configurar_periodo
from app.models.socio import Socio
from app.models.vista_socios import (
    ConfigVistaSocios, MODO_DESACTIVADO, MODO_RANGO, MODO_TODOS,
)

CONFIG_ID = 1
_NO_DIGITOS = re.compile(r"\D")


def leer_config(db: Session, bloquear: bool = False) -> Optional[ConfigVistaSocios]:
    stmt = select(ConfigVistaSocios).where(ConfigVistaSocios.id == CONFIG_ID)
    if bloquear:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def modo_vigente(config: Optional[ConfigVistaSocios]) -> str:
    return config.modo if config else MODO_DESACTIVADO


def version_vigente(config: Optional[ConfigVistaSocios]) -> int:
    return config.version if config else 1


def id_autorizado(config: Optional[ConfigVistaSocios], socio_id: int) -> bool:
    modo = modo_vigente(config)
    if modo == MODO_TODOS:
        return True
    if modo == MODO_RANGO:
        return config.id_inicio is not None and config.id_fin is not None and config.id_inicio <= socio_id <= config.id_fin
    return False


def solo_digitos(texto: str) -> str:
    """La cédula del login es solo numérica ("CE 20318620" se escribe 20318620)."""
    return _NO_DIGITOS.sub("", texto or "")


def cedula_bloqueada(digitos: str) -> bool:
    """Cédulas provisionales (11111111, 2222222222, 3333333333...): todas las cifras iguales.

    Cualquiera podría adivinarlas, así que esos socios no pueden entrar.
    """
    return len(digitos) < 5 or len(set(digitos)) == 1


def huella_cedula(digitos: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), ("socio-cedula:" + digitos).encode("utf-8"), hashlib.sha256
    ).hexdigest()


def socio_puede_entrar(config: Optional[ConfigVistaSocios], socio: Socio) -> bool:
    digitos = solo_digitos(socio.cedula)
    return bool(socio.is_active) and not cedula_bloqueada(digitos) and id_autorizado(config, socio.id)


def buscar_socio_por_cedula(db: Session, digitos: str) -> Optional[Socio]:
    """Socio del año activo cuya cédula registrada (solo sus cifras) coincide.

    Si dos cédulas registradas tienen las mismas cifras no se elige ninguna.
    """
    # Solo id y cédula: cargar el socio completo traería también sus movimientos.
    encontrados = [
        socio_id for socio_id, cedula in db.execute(select(Socio.id, Socio.cedula)).all()
        if hmac.compare_digest(solo_digitos(cedula).encode("utf-8"), digitos.encode("utf-8"))
    ]
    if len(encontrados) != 1:
        return None
    return db.get(Socio, encontrados[0])


def get_db_activo(db: Session = Depends(get_db)) -> Session:
    """Sesión ligada siempre al año activo: el portal ignora la cabecera X-Periodo."""
    configurar_periodo(db, None)
    return db
