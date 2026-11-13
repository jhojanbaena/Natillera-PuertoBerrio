"""Límite por cuenta compartido en PostgreSQL: 10 intentos por minuto."""
import hashlib
import time
from fastapi import HTTPException
from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from app.models.login_limit import LoginLimit


def check_login_limit(db: Session, username: str):
    window = int(time.time()) // 60
    key = hashlib.sha256(username.encode("utf-8")).hexdigest()
    # Eliminar ventanas antiguas; no retener nombres ni direcciones IP.
    db.execute(delete(LoginLimit).where(LoginLimit.window < window - 1))
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    stmt = insert(LoginLimit).values(key=key, window=window, attempts=1)
    stmt = stmt.on_conflict_do_update(index_elements=[LoginLimit.key], set_={
        "window": window,
        "attempts": case((LoginLimit.window == window, LoginLimit.attempts + 1), else_=1),
    }).returning(LoginLimit.attempts)
    attempts = db.execute(stmt).scalar_one()
    # Persistir incluso si la autenticación posterior falla.
    db.commit()
    if attempts > 10:
        raise HTTPException(status_code=429, detail="Demasiados intentos; inténtalo en un minuto", headers={"Retry-After": "60"})
