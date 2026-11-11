"""Fecha elegida por el usuario en aportes, multas y abonos."""
from datetime import timedelta
from decimal import Decimal

from app.services.prestamos_service import hoy_colombia

API = "/api/v1"


def liquidacion(client, anio):
    return client.get(f"{API}/finanzas/liquidacion-anual?anio={anio}").json()


def test_aporte_con_fecha_cuenta_en_su_anio(client, socio):
    anio = hoy_colombia().year
    response = client.post(f"{API}/socios/{socio['id']}/movimientos", json={
        "tipo_movimiento": "APORTE", "monto": "700", "fecha": f"{anio - 1}-12-31",
    })
    assert response.status_code == 201, response.text
    assert response.json()["fecha"].startswith(f"{anio - 1}-12-31")

    assert Decimal(liquidacion(client, anio - 1)["total_ahorro_acumulado"]) == 700
    assert Decimal(liquidacion(client, anio)["total_ahorro_acumulado"]) == 0

    # 1 de enero también queda en su año, sin correrse por la zona horaria.
    assert client.post(f"{API}/socios/{socio['id']}/movimientos", json={
        "tipo_movimiento": "APORTE", "monto": "50", "fecha": f"{anio}-01-01",
    }).status_code == 201
    assert Decimal(liquidacion(client, anio)["total_ahorro_acumulado"]) == 50


def test_aporte_sin_fecha_usa_hoy_y_rechaza_futuro(client, socio):
    assert client.post(f"{API}/socios/{socio['id']}/movimientos", json={
        "tipo_movimiento": "APORTE", "monto": "10",
    }).status_code == 201
    manana = (hoy_colombia() + timedelta(days=1)).isoformat()
    response = client.post(f"{API}/socios/{socio['id']}/movimientos", json={
        "tipo_movimiento": "APORTE", "monto": "10", "fecha": manana,
    })
    assert response.status_code == 422
    assert Decimal(liquidacion(client, hoy_colombia().year)["total_ahorro_acumulado"]) == 10


def test_abono_con_fecha_validada_y_editable(client, prestamo):
    pid = prestamo["id"]  # préstamo del 2026-01-01
    base = {"prestamo_id": pid, "monto_abonado": "150", "monto_capital": "100", "monto_interes": "50"}

    antes = client.post(f"{API}/prestamos/{pid}/abonos", json={**base, "fecha_pago": "2025-12-31"})
    assert antes.status_code == 422

    creado = client.post(f"{API}/prestamos/{pid}/abonos", json={**base, "fecha_pago": "2026-02-01"})
    assert creado.status_code == 201, creado.text
    abono = creado.json()
    assert abono["fecha_pago"].startswith("2026-02-01")

    editado = client.put(f"{API}/prestamos/{pid}/abonos/{abono['id']}", json={**base, "fecha_pago": "2026-02-05"})
    assert editado.status_code == 200, editado.text
    assert editado.json()["fecha_pago"].startswith("2026-02-05")

    # Editar sin fecha conserva la fecha existente.
    sin_fecha = client.put(f"{API}/prestamos/{pid}/abonos/{abono['id']}", json=base)
    assert sin_fecha.json()["fecha_pago"].startswith("2026-02-05")

    ediciones = sorted(
        (h for h in client.get(f"{API}/historial?tipo_accion=EDITAR").json() if h["entidad_tipo"] == "AbonoPrestamo"),
        key=lambda h: h["id"],
    )
    # Revertir la edición que cambió la fecha (la primera) devuelve la fecha original.
    assert client.post(f"{API}/historial/{ediciones[-1]['id']}/revertir").status_code == 200
    assert client.post(f"{API}/historial/{ediciones[0]['id']}/revertir").status_code == 200
    restaurado = client.get(f"{API}/prestamos/{pid}").json()["abonos"][0]
    assert restaurado["fecha_pago"].startswith("2026-02-01")
