"""Control de pagos de la liquidación anual ("Ya se liquidó"): saldo del fondo y duplicados."""
from decimal import Decimal

from app.services.prestamos_service import hoy_colombia

API = "/api/v1"
BASE = f"{API}/finanzas/liquidacion-anual"


def crear_socio_con_ahorro(client, cedula, nombre, monto):
    r = client.post(f"{API}/socios", json={
        "cedula": cedula, "nombre": nombre, "telefono": "3000000000",
        "residencia": "Calle 1", "aporte_mensual": "100.00",
    })
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    r = client.post(f"{API}/socios/{sid}/movimientos", json={"tipo_movimiento": "APORTE", "monto": monto})
    assert r.status_code in (200, 201), r.text
    return sid


def control(client, anio):
    r = client.get(f"{BASE}/control", params={"anio": anio})
    assert r.status_code == 200, r.text
    return r.json()


def test_pago_descuenta_saldo_y_no_se_duplica(client):
    anio = hoy_colombia().year
    a = crear_socio_con_ahorro(client, "1111111", "Ana", "5000.00")
    b = crear_socio_con_ahorro(client, "2222222", "Beto", "3000.00")

    inicial = control(client, anio)
    assert Decimal(inicial["monto_general"]) == Decimal("8000.00")
    assert inicial["fondo_definido"] is False
    assert inicial["total_pendientes"] == 2

    r = client.post(f"{BASE}/pagos", json={"anio": anio, "socio_id": a})
    assert r.status_code == 201, r.text
    assert Decimal(r.json()["monto"]) == Decimal("5000.00")

    estado = control(client, anio)
    assert estado["fondo_definido"] is True
    assert Decimal(estado["monto_utilizado"]) == Decimal("5000.00")
    assert Decimal(estado["saldo_disponible"]) == Decimal("3000.00")
    item_a = next(s for s in estado["socios"] if s["socio_id"] == a)
    # Solo queda marcado como liquidado: no se registra método de pago.
    assert item_a["liquidado"] and item_a["pago"]["metodo_pago"] is None

    # Segundo intento sobre el mismo socio: rechazado y el saldo no cambia.
    r = client.post(f"{BASE}/pagos", json={"anio": anio, "socio_id": a})
    assert r.status_code == 409
    assert Decimal(control(client, anio)["saldo_disponible"]) == Decimal("3000.00")

    r = client.post(f"{BASE}/pagos", json={"anio": anio, "socio_id": b})
    assert r.status_code == 201, r.text
    assert Decimal(control(client, anio)["saldo_disponible"]) == Decimal("0.00")


def test_saldo_insuficiente_y_reversion(client):
    anio = hoy_colombia().year
    a = crear_socio_con_ahorro(client, "3333333", "Carla", "5000.00")
    b = crear_socio_con_ahorro(client, "4444444", "Dario", "3000.00")

    # El fondo no puede quedar por debajo de lo entregado; aquí se fija en 6000.
    r = client.put(f"{BASE}/fondo", json={"anio": anio, "monto_general": "6000.00"})
    assert r.status_code == 200, r.text

    pago_a = client.post(f"{BASE}/pagos", json={"anio": anio, "socio_id": a}).json()
    r = client.post(f"{BASE}/pagos", json={"anio": anio, "socio_id": b})
    assert r.status_code == 409 and "insuficiente" in r.json()["detail"]

    r = client.put(f"{BASE}/fondo", json={"anio": anio, "monto_general": "4000.00"})
    assert r.status_code == 409

    # Ya no existe el cambio de método de pago.
    assert client.put(f"{BASE}/pagos/{pago_a['id']}", json={"metodo_pago": "TRANSFERENCIA"}).status_code == 405
    assert Decimal(control(client, anio)["saldo_disponible"]) == Decimal("1000.00")

    r = client.delete(f"{BASE}/pagos/{pago_a['id']}")
    assert r.status_code == 204
    estado = control(client, anio)
    assert Decimal(estado["saldo_disponible"]) == Decimal("6000.00")
    assert estado["total_liquidados"] == 0
    assert client.delete(f"{BASE}/pagos/{pago_a['id']}").status_code == 404


def test_solo_admin_registra_pagos(client):
    from app.core.security import create_access_token
    anio = hoy_colombia().year
    a = crear_socio_con_ahorro(client, "5555555", "Elena", "1000.00")
    r = client.post(
        f"{BASE}/pagos", json={"anio": anio, "socio_id": a},
        headers={"Authorization": "Bearer " + create_access_token("reader-test")},
    )
    assert r.status_code == 403
