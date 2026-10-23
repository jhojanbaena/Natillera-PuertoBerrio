"""Regresiones de seguridad, atomicidad y despliegue."""
import hashlib
import time
import jwt
import pytest
from sqlalchemy import select, text, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import Settings, settings
from app.core.security import get_password_hash, verify_password, decode_access_token
from app.models import Actividad, AbonoPrestamo
from app.models.login_limit import LoginLimit
from manage_db import audit, upgrade

API = "/api/v1"


def test_password_no_truncation():
    hashed = get_password_hash("a" * 72)
    assert verify_password("a" * 72, hashed)
    assert not verify_password("a" * 72 + "suffix", hashed)
    with pytest.raises(ValueError, match="72 bytes"):
        get_password_hash("á" * 37)


def test_jwt_requires_expiration():
    token = jwt.encode({"sub": "admin-test"}, settings.SECRET_KEY, algorithm="HS256")
    assert decode_access_token(token) is None


def test_unicode_password_limit(client):
    assert client.post(API + "/auth/register", json={"username": "unicode-test", "password": "á" * 37}).status_code == 422


def test_shared_login_limit(client, database_engine):
    with Session(database_engine) as db:
        db.add(LoginLimit(key=hashlib.sha256(b"admin-test").hexdigest(), window=int(time.time()) // 60, attempts=10))
        db.commit()
    for path, kwargs in [("login-json", {"json": {"username": "admin-test", "password": "test-password"}}), ("login", {"data": {"username": "admin-test", "password": "test-password"}})]:
        response = client.post(API + "/auth/" + path, **kwargs)
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"


def test_audit_failure_rolls_back(client, database_engine, monkeypatch):
    from app.routers import actividades
    def fail(*args, **kwargs):
        raise RuntimeError("simulated audit failure")
    monkeypatch.setattr(actividades, "registrar_movimiento", fail)
    with pytest.raises(RuntimeError, match="simulated"):
        client.post(API + "/actividades", json={"nombre": "Venta", "grupo_encargado": "Grupo", "fecha": "2026-10-21", "inversion": "10", "ingresos_brutos": "20"})
    with Session(database_engine) as db:
        assert db.execute(select(Actividad)).first() is None


@pytest.mark.parametrize("amount", ["0.001", "10000000000", "NaN", "Infinity"])
def test_money_validation(client, socio, amount):
    response = client.post(f"{API}/socios/{socio['id']}/movimientos", json={"tipo_movimiento": "APORTE", "monto": amount})
    assert response.status_code == 422


def test_database_rejects_invalid_abono(client, prestamo, database_engine):
    with database_engine.connect() as connection:
        with pytest.raises(IntegrityError, match="ck_abono_importes"):
            connection.execute(insert(AbonoPrestamo).values(prestamo_id=prestamo["id"], monto_abonado=100, monto_capital=90, monto_interes=20, numero_cuota=1))
        connection.rollback()


def test_undo_deposit_preserves_savings(client, socio):
    sid = socio["id"]
    for kind in ["APORTE", "RETIRO_AHORRO"]:
        assert client.post(f"{API}/socios/{sid}/movimientos", json={"tipo_movimiento": kind, "monto": "100"}).status_code == 201
    logs = client.get(API + "/historial").json()
    deposit = next(log for log in logs if log["entidad_tipo"] == "FinanzaSocio" and "APORTE" in log["descripcion"])
    assert client.post(f"{API}/historial/{deposit['id']}/revertir").status_code == 409


def test_stale_undo_preserves_newer_note(client):
    note = client.post(API + "/notas", json={"contenido": "original"}).json()
    for content in ["edición uno", "edición dos"]:
        assert client.put(f"{API}/notas/{note['id']}", json={"contenido": content}).status_code == 200
    edits = sorted(client.get(API + "/historial?tipo_accion=EDITAR").json(), key=lambda log: log["id"])
    assert client.post(f"{API}/historial/{edits[0]['id']}/revertir").status_code == 409
    assert client.get(f"{API}/notas/{note['id']}").json()["contenido"] == "edición dos"


def test_production_configuration():
    with pytest.raises(ValueError, match="AUTO_CREATE_TABLES"):
        Settings(ENVIRONMENT="production", _env_file=None)
    with pytest.raises(ValueError, match="sslmode"):
        Settings(ENVIRONMENT="production", AUTO_CREATE_TABLES=False, BACKEND_CORS_ORIGINS="https://app.example.com", _env_file=None)


def test_security_headers_and_cors(client):
    response = client.get(API + "/socios")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    response = client.options(API + "/socios", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "Access-Control-Allow-Origin" not in response.headers


def test_postgres_migration_twice_and_drift(client, database_engine, prestamo):
    if database_engine.dialect.name != "postgresql":
        pytest.skip("DDL y bloqueos PostgreSQL")
    with database_engine.begin() as connection:
        schema = connection.get_execution_options()["schema_translate_map"][None]
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        upgrade(connection)
        upgrade(connection)
        assert not audit(connection)
        connection.execute(text("UPDATE prestamos SET cuotas_pagadas = 5"))
        assert audit(connection)["prestamos_descuadrados"] == 1
