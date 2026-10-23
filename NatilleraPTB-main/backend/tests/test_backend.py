"""Contratos HTTP y regresión de reglas financieras."""
from datetime import timedelta
from decimal import Decimal

import pytest

from app.core.security import create_access_token, decode_access_token, verify_password

API = "/api/v1"


def test_root_and_openapi(client):
    assert client.get("/").json()["status"] == "online"
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert API + "/auth/login" in schema.json()["paths"]


@pytest.mark.parametrize("path", ["/socios", "/prestamos", "/rifas", "/actividades", "/reuniones", "/notas", "/historial", "/programacion", "/dashboard", "/finanzas"])
def test_authentication_required(client, path):
    client.headers.pop("Authorization")
    assert client.get(API + path).status_code == 401


@pytest.mark.parametrize("mode", ["login", "login-json"])
def test_login(client, mode):
    credentials = {"username": "admin-test", "password": "test-password"}
    response = client.post(API + "/auth/" + mode, **{
        "data" if mode == "login" else "json": credentials,
    })
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert decode_access_token(token)["sub"] == "admin-test"
    profile = client.get(API + "/auth/me", headers={"Authorization": "Bearer " + token})
    assert profile.status_code == 200
    assert "password_hash" not in profile.json()


@pytest.mark.parametrize("username,password,expected", [
    ("admin-test", "wrong", 401), ("missing-user", "test-password", 401),
    ("inactive-test", "test-password", 403),
])
def test_login_errors(client, username, password, expected):
    assert client.post(API + "/auth/login-json", json={
        "username": username, "password": password,
    }).status_code == expected


def test_tokens_and_password(password_hash):
    assert verify_password("test-password", password_hash)
    assert not verify_password("wrong", password_hash)
    assert decode_access_token("invalid-token") is None
    assert decode_access_token(create_access_token("admin-test", timedelta(seconds=-1))) is None


@pytest.mark.parametrize("token", ["malformed", create_access_token("missing-user"), create_access_token("admin-test", timedelta(seconds=-1))])
def test_invalid_bearer_rejected(client, token):
    assert client.get(API + "/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_cors_and_month_validation(client):
    response = client.options(API + "/socios", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    response = client.options(API + "/socios", headers={
        "Origin": "https://untrusted.invalid", "Access-Control-Request-Method": "GET",
    })
    assert "access-control-allow-origin" not in response.headers
    assert client.get(API + "/programacion?mes=13").status_code == 422


def test_reader_cannot_write_or_register(client):
    client.headers["Authorization"] = "Bearer " + create_access_token("reader-test")
    assert client.post(API + "/socios", json={}).status_code == 403
    assert client.post(API + "/auth/register", json={
        "username": "new-user", "password": "password12345",
    }).status_code == 403
    assert client.get(API + "/socios").status_code == 200


def test_admin_register_cannot_escalate(client):
    body = {"username": "new-user", "password": "password12345"}
    assert client.post(API + "/auth/register", json={**body, "is_admin": True}).status_code == 422
    response = client.post(API + "/auth/register", json=body)
    assert response.status_code == 201
    assert response.json()["is_admin"] is False
    assert client.post(API + "/auth/register", json=body).status_code == 400


def test_socio_crud_and_validation(client, socio):
    assert client.get(API + "/socios").json()[0]["id"] == socio["id"]
    assert client.post(API + "/socios", json=socio).status_code == 400
    assert client.put(API + f"/socios/{socio['id']}", json={"nombre": "Nombre actualizado"}).status_code == 200
    assert client.get(API + f"/socios/{socio['id']}").json()["nombre"] == "Nombre actualizado"
    assert client.get(API + "/socios/99999").status_code == 404
    assert client.get(API + "/socios?limit=501").status_code == 422
    assert client.put(API + f"/socios/{socio['id']}", json={"aporte_mensual": -1}).status_code == 422
    assert client.delete(API + f"/socios/{socio['id']}").status_code == 200


def test_financial_movements_and_capital(client, socio):
    for kind, amount in [("APORTE", "100.00"), ("RETIRO_AHORRO", "20.00"), ("MULTA", "15.00"), ("PAGO_MULTA", "5.00")]:
        response = client.post(API + f"/socios/{socio['id']}/movimientos", json={"tipo_movimiento": kind, "monto": amount})
        assert response.status_code == 201, response.text
    profile = client.get(API + f"/socios/{socio['id']}/perfil").json()
    assert Decimal(profile["total_ahorrado"]) == 80
    assert Decimal(profile["total_multas_pendientes"]) == 10
    capital = client.get(API + "/finanzas/capital-total").json()
    assert Decimal(capital["capital_total"]) == 85
    assert Decimal(capital["liquidez_disponible_caja"]) == 85


def test_loan_payment_and_undo(client, prestamo):
    pid = prestamo["id"]
    assert Decimal(prestamo["total_intereses"]) == 200
    response = client.post(API + f"/prestamos/{pid}/abonos", json={
        "prestamo_id": pid, "monto_abonado": "600", "monto_capital": "500", "monto_interes": "100",
    })
    assert response.status_code == 201, response.text
    assert Decimal(client.get(API + f"/prestamos/{pid}").json()["saldo_pendiente"]) == 500
    history = client.get(API + "/historial", params={"tipo_accion": "CREAR"}).json()
    hid = next(h["id"] for h in history if h["entidad_tipo"] == "AbonoPrestamo")
    assert client.post(API + f"/historial/{hid}/revertir").status_code == 200
    loan = client.get(API + f"/prestamos/{pid}").json()
    assert Decimal(loan["saldo_pendiente"]) == 1000
    assert loan["cuotas_pagadas"] == 0
    assert client.post(API + f"/historial/{hid}/revertir").status_code == 400


def test_invalid_payment_breakdown(client, prestamo):
    assert client.post(API + f"/prestamos/{prestamo['id']}/abonos", json={
        "prestamo_id": prestamo["id"], "monto_abonado": "100", "monto_capital": "90", "monto_interes": "20",
    }).status_code == 422


@pytest.mark.parametrize("resource,body,profit_field,profit", [
    ("actividades", {"nombre": "Actividad prueba", "grupo_encargado": "Grupo uno", "fecha": "2026-10-25", "inversion": "100", "ingresos_brutos": "250"}, "ganancia_neta", 150),
    ("rifas", {"nombre": "Rifa prueba", "fecha": "2026-10-25", "inversion_premios": "100", "valor_boleta": "10", "total_boletas": 30, "boletas_vendidas": 20}, "ganancias_totales", 100),
    ("reuniones", {"fecha": "2026-10-25", "hora": "19:00", "lugar": "Sede prueba", "tema": "Balance", "ganancias_reunion": "50"}, "ganancias_reunion", 50),
    ("notas", {"titulo": "Nota prueba", "contenido": "Actividad agendada", "fecha_programada": "2026-10-25"}, None, None),
])
def test_events_crud_schedule_and_restore(client, resource, body, profit_field, profit):
    response = client.post(API + "/" + resource, json=body)
    assert response.status_code == 201, response.text
    item = response.json()
    if profit_field:
        assert Decimal(item[profit_field]) == profit
    assert client.get(API + f"/{resource}/{item['id']}").status_code == 200
    schedule = client.get(API + "/programacion?mes=10&anio=2026")
    assert schedule.status_code == 200, schedule.text
    assert any(e["fecha"] == "2026-10-25" for e in schedule.json()["eventos"])
    assert client.put(API + f"/{resource}/{item['id']}", json=body).status_code == 200
    assert client.delete(API + f"/{resource}/{item['id']}").status_code == 200
    history = client.get(API + "/historial?tipo_accion=ELIMINAR").json()
    assert client.post(API + f"/historial/{history[0]['id']}/revertir").status_code == 200
    assert client.get(API + f"/{resource}/{item['id']}").status_code == 200


@pytest.mark.parametrize("path", ["/dashboard", "/finanzas/liquidacion-anual", "/finanzas/bien-comun", "/historial/resumen", "/prestamos/consolidado/global", "/actividades/resumen/balance", "/rifas/resumen/metricas"])
def test_empty_reports(client, path):
    response = client.get(API + path)
    assert response.status_code == 200, response.text


def test_liquidation_distributes_activity_profit(client, socio):
    """El contrato documenta reparto de utilidades; 100 de ahorro + 50 de ganancia."""
    assert client.post(API + f"/socios/{socio['id']}/movimientos", json={"tipo_movimiento": "APORTE", "monto": "100"}).status_code == 201
    assert client.post(API + "/actividades", json={"nombre": "Venta", "grupo_encargado": "Grupo", "fecha": "2026-10-20", "inversion": "50", "ingresos_brutos": "100"}).status_code == 201
    result = client.get(API + "/finanzas/liquidacion-anual").json()
    assert Decimal(result["total_utilidades_generadas"]) == 50
    assert Decimal(result["gran_total_a_entregar"]) == 150


def test_loan_remains_open_until_interest_is_paid(client, prestamo):
    pid = prestamo["id"]
    assert client.post(API + f"/prestamos/{pid}/abonos", json={
        "prestamo_id": pid, "monto_abonado": "1000", "monto_capital": "1000", "monto_interes": "0",
    }).status_code == 201
    loan = client.get(API + f"/prestamos/{pid}").json()
    assert Decimal(loan["total_intereses"]) == 200
    assert loan["estado"] != "PAGADO"


def test_rejects_oversold_raffle(client):
    response = client.post(API + "/rifas", json={
        "nombre": "Rifa imposible", "fecha": "2026-10-25", "total_boletas": 10,
        "boletas_vendidas": 11, "valor_boleta": "10",
    })
    assert response.status_code == 422


def test_rejects_withdrawal_exceeding_savings(client, socio):
    response = client.post(API + f"/socios/{socio['id']}/movimientos", json={
        "tipo_movimiento": "RETIRO_AHORRO", "monto": "100",
    })
    assert response.status_code in (400, 422)


def test_payment_edit_can_be_reverted(client, prestamo):
    pid = prestamo["id"]
    payment = client.post(API + f"/prestamos/{pid}/abonos", json={
        "prestamo_id": pid, "monto_abonado": "500", "monto_capital": "500",
    }).json()
    assert client.put(API + f"/prestamos/{pid}/abonos/{payment['id']}", json={
        "prestamo_id": pid, "monto_abonado": "400", "monto_capital": "400",
    }).status_code == 200
    history = client.get(API + "/historial?tipo_accion=EDITAR").json()
    edits = [h for h in history if h["entidad_tipo"] == "AbonoPrestamo"]
    assert edits, "Editar un abono no genera historial: la corrección no puede revertirse"
    assert client.post(API + f"/historial/{edits[0]['id']}/revertir").status_code == 200
    loan = client.get(API + f"/prestamos/{pid}").json()
    assert Decimal(loan["saldo_pendiente"]) == 500


def test_deleted_socio_restore_keeps_loans(client, socio, prestamo):
    """Restaurar un socio debe recuperar la cartera eliminada en cascada."""
    assert client.delete(API + f"/socios/{socio['id']}?hard_delete=true").status_code == 200
    assert client.get(API + f"/prestamos/{prestamo['id']}").status_code == 404
    history = client.get(API + "/historial?tipo_accion=ELIMINAR").json()
    assert client.post(API + f"/historial/{history[0]['id']}/revertir").status_code == 200
    assert client.get(API + f"/socios/{socio['id']}").status_code == 200
    assert client.get(API + f"/prestamos/{prestamo['id']}").status_code == 200
