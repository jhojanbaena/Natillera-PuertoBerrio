"""Operaciones sobre socios que afectan a varias tablas."""
from fastapi import HTTPException, status
from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from app.models.finanzas import FinanzaSocio
from app.models.historial import HistorialMovimiento
from app.models.prestamo import Prestamo
from app.models.socio import Socio


def cambiar_id_socio(db: Session, socio: Socio, nuevo_id: int) -> Socio:
    """Cambia el ID de un socio y mueve sus aportes, multas, préstamos e historial al nuevo ID.

    El ID es la clave primaria referenciada por otras tablas, así que no se puede
    actualizar en sitio: se crea la fila con el ID nuevo, se reasignan los registros
    dependientes y se elimina la fila anterior, todo en la misma transacción.
    """
    viejo_id = socio.id
    if nuevo_id == viejo_id:
        return socio
    if db.execute(select(Socio.id).where(Socio.id == nuevo_id)).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ya existe un socio registrado con el ID {nuevo_id}",
        )

    db.flush()
    valores = {columna.key: getattr(socio, columna.key) for columna in Socio.__table__.columns}
    sin_orm = {"synchronize_session": False}

    # Liberar la cédula (única) mientras coexisten las dos filas.
    db.execute(update(Socio).where(Socio.id == viejo_id).values(cedula=f"~mov{viejo_id}"[:20]),
               execution_options=sin_orm)
    db.execute(insert(Socio).values(**{**valores, "id": nuevo_id}))
    for modelo in (FinanzaSocio, Prestamo):
        db.execute(update(modelo).where(modelo.socio_id == viejo_id).values(socio_id=nuevo_id),
                   execution_options=sin_orm)
    db.execute(
        update(HistorialMovimiento)
        .where(HistorialMovimiento.entidad_tipo == "Socio", HistorialMovimiento.entidad_id == viejo_id)
        .values(entidad_id=nuevo_id),
        execution_options=sin_orm,
    )
    # Sacar el objeto de la sesión evita que el ORM borre en cascada lo que ya se movió.
    db.expunge(socio)
    db.execute(delete(Socio).where(Socio.id == viejo_id), execution_options=sin_orm)
    db.expire_all()
    return db.execute(select(Socio).where(Socio.id == nuevo_id)).scalar_one()
