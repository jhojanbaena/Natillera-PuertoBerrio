"""Casos límite de los seis defectos financieros y de reversión."""
from decimal import Decimal
import pytest

API = "/api/v1"


def movement(client, socio_id, kind, amount):
    response = client.post(f"{API}/socios/{socio_id}/movimientos", json={
        "tipo_movimiento": kind, "monto": str(amount),
    })
    assert response.status_code == 201, response.text
    return response.json()


def payment(client, loan_id, capital, interest=0, number=None):
    response = client.post(f"{API}/prestamos/{loan_id}/abonos", json={
        "prestamo_id": loan_id, "monto_abonado": str(Decimal(str(capital)) + Decimal(str(interest))),
        "monto_capital": str(capital), "monto_interes": str(interest),
        "numero_cuota": number,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_interest_only_final_payment_and_undo(client, prestamo):
    pid = prestamo["id"]
    payment(client, pid, 1000)
    final = payment(client, pid, 0, 200)
    assert client.get(f"{API}/prestamos/{pid}").json()["estado"] == "PAGADO"
    assert client.post(f"{API}/prestamos/{pid}/abonos", json={
        "prestamo_id": pid, "monto_abonado": "1",
    }).status_code == 400
    log = next(h for h in client.get(f"{API}/historial").json()
               if h["entidad_tipo"] == "AbonoPrestamo" and h["entidad_id"] == final["id"])
    assert client.post(f"{API}/historial/{log['id']}/revertir").status_code == 200
    loan = client.get(f"{API}/prestamos/{pid}").json()
    assert loan["estado"] == "PENDIENTE"
    assert loan["cuotas_pagadas"] == 1
    assert Decimal(loan["saldo_pendiente"]) == 0


def test_zero_interest_loan_closes_on_capital_payment(client, socio):
    loan = client.post(f"{API}/prestamos", json={
        "socio_id": socio["id"], "monto_prestado": "100", "numero_cuotas": 1,
    }).json()
    payment(client, loan["id"], 100)
    assert client.get(f"{API}/prestamos/{loan['id']}").json()["estado"] == "PAGADO"


def test_edit_payment_undo_restores_interest_and_status(client, prestamo):
    pid = prestamo["id"]
    original = payment(client, pid, 1000, 200)
    response = client.put(f"{API}/prestamos/{pid}/abonos/{original['id']}", json={
        "prestamo_id": pid, "monto_abonado": "1000", "monto_capital": "1000", "monto_interes": "0",
    })
    assert response.status_code == 200
    assert client.get(f"{API}/prestamos/{pid}").json()["estado"] == "PENDIENTE"
    log = next(h for h in client.get(f"{API}/historial?tipo_accion=EDITAR").json()
               if h["entidad_tipo"] == "AbonoPrestamo")
    assert client.post(f"{API}/historial/{log['id']}/revertir").status_code == 200
    restored = client.get(f"{API}/prestamos/{pid}").json()
    assert restored["estado"] == "PAGADO"
    assert restored["cuotas_pagadas"] == 1
    assert restored["abonos"][0] == original


def test_restore_socio_keeps_loan_payments_and_dates(client, socio, prestamo):
    payment(client, prestamo["id"], 400, 100)
    movement(client, socio["id"], "APORTE", 500)
    before_loan = client.get(f"{API}/prestamos/{prestamo['id']}").json()
    before_profile = client.get(f"{API}/socios/{socio['id']}/perfil").json()
    assert client.delete(f"{API}/socios/{socio['id']}?hard_delete=true").status_code == 200
    log = client.get(f"{API}/historial?tipo_accion=ELIMINAR").json()[0]
    assert client.post(f"{API}/historial/{log['id']}/revertir").status_code == 200
    assert client.get(f"{API}/prestamos/{prestamo['id']}").json() == before_loan
    assert client.get(f"{API}/socios/{socio['id']}/perfil").json() == before_profile


def test_withdrawal_exact_balance_then_reject_extra(client, socio):
    sid = socio["id"]
    movement(client, sid, "APORTE", "100.01")
    movement(client, sid, "RETIRO_AHORRO", "100.01")
    response = client.post(f"{API}/socios/{sid}/movimientos", json={
        "tipo_movimiento": "RETIRO_AHORRO", "monto": "0.01",
    })
    assert response.status_code == 422
    profile = client.get(f"{API}/socios/{sid}/perfil").json()
    assert Decimal(profile["total_ahorrado"]) == 0
    assert len(profile["historial_finanzas"]) == 2


@pytest.mark.parametrize("change", [{"boletas_vendidas": 11}, {"total_boletas": 4}])
def test_raffle_partial_edit_validates_combined_state(client, change):
    rifa = client.post(f"{API}/rifas", json={
        "nombre": "Rifa", "fecha": "2026-10-21", "total_boletas": 10, "boletas_vendidas": 5,
    }).json()
    assert client.put(f"{API}/rifas/{rifa['id']}", json=change).status_code == 422
    restored = client.get(f"{API}/rifas/{rifa['id']}").json()
    assert restored["total_boletas"] == 10
    assert restored["boletas_vendidas"] == 5
    assert client.put(f"{API}/rifas/{rifa['id']}", json={
        "total_boletas": 20, "boletas_vendidas": 20,
    }).status_code == 200


def test_liquidation_preserves_all_funds_without_double_interest(client, socio, prestamo):
    movement(client, socio["id"], "APORTE", 2000)
    movement(client, socio["id"], "PAGO_MULTA", 10)
    payment(client, prestamo["id"], 1000, 100, 1)
    payment(client, prestamo["id"], 0, 100, 4)
    assert client.post(f"{API}/actividades", json={
        "nombre": "Venta", "grupo_encargado": "Grupo", "fecha": "2026-10-21",
        "inversion": "50", "ingresos_brutos": "100",
    }).status_code == 201
    result = client.get(f"{API}/finanzas/liquidacion-anual").json()
    item = result["socios_liquidados"][0]
    assert Decimal(item["total_ahorrado"]) == 2100
    assert Decimal(item["bien_comun_asignado"]) == 110
    assert Decimal(item["utilidad_ganada"]) == 50
    assert Decimal(result["gran_total_a_entregar"]) == 2260


def test_liquidation_proportional_profit_and_cent_conservation(client, socio):
    members = [socio]
    for i in range(2):
        response = client.post(f"{API}/socios", json={
            "cedula": f"999999{i}", "nombre": f"Otro {i}", "telefono": "3001234567",
            "residencia": "Calle prueba", "aporte_mensual": "100",
        })
        assert response.status_code == 201
        members.append(response.json())
    for member in members:
        movement(client, member["id"], "APORTE", 100)
    movement(client, socio["id"], "PAGO_MULTA", 1)
    assert client.post(f"{API}/rifas", json={
        "nombre": "Rifa", "fecha": "2026-10-21", "total_boletas": 1,
        "boletas_vendidas": 1, "valor_boleta": "1",
    }).status_code == 201
    result = client.get(f"{API}/finanzas/liquidacion-anual").json()
    items = result["socios_liquidados"]
    assert sum(Decimal(i["utilidad_ganada"]) for i in items) == 1
    assert sum(Decimal(i["bien_comun_asignado"]) for i in items) == 1
    assert Decimal(result["gran_total_a_entregar"]) == 302
    movement(client, socio["id"], "APORTE", 200)
    result = client.get(f"{API}/finanzas/liquidacion-anual").json()
    first = next(i for i in result["socios_liquidados"] if i["socio_id"] == socio["id"])
    assert Decimal(first["utilidad_ganada"]) == Decimal("0.60")


def test_payment_undo_rejects_stale_edit_then_allows_latest_first(client, prestamo):
    pid = prestamo["id"]
    abono = payment(client, pid, 500)
    logs = []
    for amount in (400, 300):
        assert client.put(f"{API}/prestamos/{pid}/abonos/{abono['id']}", json={
            "prestamo_id": pid, "monto_abonado": str(amount), "monto_capital": str(amount),
        }).status_code == 200
        logs.append(max(h["id"] for h in client.get(f"{API}/historial?tipo_accion=EDITAR").json()))
    assert client.post(f"{API}/historial/{logs[0]}/revertir").status_code == 409
    assert client.post(f"{API}/historial/{logs[1]}/revertir").status_code == 200
    assert client.post(f"{API}/historial/{logs[0]}/revertir").status_code == 200
    loan = client.get(f"{API}/prestamos/{pid}").json()
    assert loan["abonos"][0] == abono


def test_payment_edit_rollback_when_audit_fails(client, prestamo, monkeypatch):
    pid = prestamo["id"]
    original = payment(client, pid, 500)
    from app.routers import prestamos

    def fail_audit(**kwargs):
        raise RuntimeError("Fallo de auditoría simulado")

    monkeypatch.setattr(prestamos, "registrar_movimiento", fail_audit)
    with pytest.raises(RuntimeError, match="auditoría simulado"):
        client.put(f"{API}/prestamos/{pid}/abonos/{original['id']}", json={
            "prestamo_id": pid, "monto_abonado": "400", "monto_capital": "400",
        })
    loan = client.get(f"{API}/prestamos/{pid}").json()
    assert Decimal(loan["saldo_pendiente"]) == 500
    assert loan["abonos"][0] == original


def test_undo_edit_cannot_overpay_after_later_payment(client, prestamo):
    pid = prestamo["id"]
    abono = payment(client, pid, 500)
    assert client.put(f"{API}/prestamos/{pid}/abonos/{abono['id']}", json={
        "prestamo_id": pid, "monto_abonado": "100", "monto_capital": "100",
    }).status_code == 200
    log = client.get(f"{API}/historial?tipo_accion=EDITAR").json()[0]
    payment(client, pid, 900)
    assert client.post(f"{API}/historial/{log['id']}/revertir").status_code == 409
    loan = client.get(f"{API}/prestamos/{pid}").json()
    assert Decimal(loan["saldo_pendiente"]) == 0
    assert len(loan["abonos"]) == 2


def test_concurrent_withdrawals_do_not_overdraw_postgres(client, socio):
    import os
    if not os.environ.get("TEST_DATABASE_URL"):
        pytest.skip("La concurrencia requiere PostgreSQL real")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.security import create_access_token

    sid = socio["id"]
    movement(client, sid, "APORTE", 100)
    barrier = Barrier(2)

    def withdraw():
        with_client = TestClient(app)
        try:
            barrier.wait(timeout=10)
            return with_client.post(f"{API}/socios/{sid}/movimientos", headers={
                "Authorization": "Bearer " + create_access_token("admin-test"),
            }, json={"tipo_movimiento": "RETIRO_AHORRO", "monto": "100"}).status_code
        finally:
            with_client.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        codes = list(executor.map(lambda _: withdraw(), range(2)))
    assert sorted(codes) == [201, 422]
    profile = client.get(f"{API}/socios/{sid}/perfil").json()
    assert len(profile["historial_finanzas"]) == 2
    assert Decimal(profile["total_ahorrado"]) == 0


def test_restore_does_not_overwrite_reused_socio_id(client, socio, prestamo):
    sid = socio["id"]
    assert client.delete(f"{API}/socios/{sid}?hard_delete=true").status_code == 200
    log = client.get(f"{API}/historial?tipo_accion=ELIMINAR").json()[0]
    replacement = client.post(f"{API}/socios", json={
        "id": sid, "cedula": "99999888", "nombre": "Nuevo socio", "telefono": "3001234567",
        "residencia": "Calle prueba", "aporte_mensual": "100",
    })
    assert replacement.status_code == 201
    assert client.post(f"{API}/historial/{log['id']}/revertir").status_code == 409
    assert client.get(f"{API}/socios/{sid}").json()["cedula"] == "99999888"
    assert client.get(f"{API}/prestamos/{prestamo['id']}").status_code == 404


@pytest.mark.parametrize("amount", ["1.00", "-1.00"])
def test_money_distribution_preserves_cents_and_losses(amount):
    from app.services.finanzas_service import repartir_importe
    parts = repartir_importe(Decimal(amount), [Decimal("1")] * 3)
    assert sum(parts) == Decimal(amount)
    assert abs(parts[0]) == Decimal("0.34")
    assert abs(parts[1]) == abs(parts[2]) == Decimal("0.33")
