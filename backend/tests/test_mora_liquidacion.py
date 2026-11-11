"""Mora automática por cuotas atrasadas y liquidación por ciclo anual."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.services.prestamos_service import (
    DIAS_GRACIA_MORA, cuotas_atrasadas, esta_en_mora, fecha_proxima_cuota, hoy_colombia, sumar_meses,
)

API = "/api/v1"


def loan(fecha_prestamo, numero_cuotas=3, cuotas_pagadas=0, estado="PENDIENTE", fecha_vencimiento=None):
    return SimpleNamespace(
        fecha_prestamo=fecha_prestamo, numero_cuotas=numero_cuotas, cuotas_pagadas=cuotas_pagadas,
        estado=estado, fecha_vencimiento=fecha_vencimiento,
    )


def test_sumar_meses_respeta_fin_de_mes():
    assert sumar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert sumar_meses(date(2026, 11, 15), 2) == date(2027, 1, 15)
    assert sumar_meses(date(2026, 3, 10), -3) == date(2025, 12, 10)


def test_mora_respeta_dias_de_gracia():
    prestamo = loan(date(2026, 1, 10))
    # La cuota 1 vence el 2026-02-10; dentro de la gracia aún no hay mora.
    assert not esta_en_mora(prestamo, date(2026, 2, 10) + timedelta(days=DIAS_GRACIA_MORA))
    assert esta_en_mora(prestamo, date(2026, 2, 11) + timedelta(days=DIAS_GRACIA_MORA))
    assert cuotas_atrasadas(prestamo, date(2026, 3, 20)) == 2


def test_mora_se_quita_al_ponerse_al_dia_y_por_vencimiento():
    hoy = date(2026, 3, 20)
    assert not esta_en_mora(loan(date(2026, 1, 10), cuotas_pagadas=2), hoy)
    # Todas las cuotas pagadas pero pasó la fecha límite con deuda pendiente.
    vencido = loan(date(2025, 1, 10), numero_cuotas=2, cuotas_pagadas=2, fecha_vencimiento=date(2025, 3, 10))
    assert esta_en_mora(vencido, hoy)
    assert cuotas_atrasadas(loan(date(2025, 1, 1), estado="PAGADO"), hoy) == 0


def test_fecha_proxima_cuota():
    assert fecha_proxima_cuota(loan(date(2026, 1, 10), cuotas_pagadas=1)) == date(2026, 3, 10)
    assert fecha_proxima_cuota(loan(date(2026, 1, 10), estado="PAGADO")) is None


def test_prestamo_atrasado_entra_y_sale_de_mora(client, socio):
    hoy = hoy_colombia()
    inicio = sumar_meses(hoy, -2) - timedelta(days=DIAS_GRACIA_MORA + 5)
    response = client.post(f"{API}/prestamos", json={
        "socio_id": socio["id"], "monto_prestado": "600", "tasa_interes": "0",
        "numero_cuotas": 6, "fecha_prestamo": inicio.isoformat(),
    })
    assert response.status_code == 201, response.text
    pid = response.json()["id"]

    detalle = client.get(f"{API}/prestamos/{pid}").json()
    assert detalle["estado"] == "EN_MORA"
    assert detalle["cuotas_atrasadas"] == 2
    assert client.get(f"{API}/dashboard").json()["total_prestamos_en_mora"] == 1
    assert [p["id"] for p in client.get(f"{API}/prestamos?estado=EN_MORA").json()] == [pid]

    for _ in range(2):
        assert client.post(f"{API}/prestamos/{pid}/abonos", json={
            "prestamo_id": pid, "monto_abonado": "100",
        }).status_code == 201
    detalle = client.get(f"{API}/prestamos/{pid}").json()
    assert detalle["estado"] == "PENDIENTE"
    assert detalle["cuotas_atrasadas"] == 0
    assert detalle["fecha_proxima_cuota"] == sumar_meses(inicio, 3).isoformat()


def test_prestamo_nuevo_no_esta_en_mora(client, socio):
    response = client.post(f"{API}/prestamos", json={
        "socio_id": socio["id"], "monto_prestado": "100", "numero_cuotas": 3,
    })
    assert response.json()["estado"] == "PENDIENTE"
    assert client.get(f"{API}/dashboard").json()["total_prestamos_en_mora"] == 0


def movement(client, socio_id, kind, amount):
    response = client.post(f"{API}/socios/{socio_id}/movimientos", json={
        "tipo_movimiento": kind, "monto": str(amount),
    })
    assert response.status_code == 201, response.text


def test_liquidacion_solo_cuenta_el_anio_elegido(client, socio):
    anio = hoy_colombia().year
    movement(client, socio["id"], "APORTE", 500)
    for fecha, ingresos in ((f"{anio - 1}-06-01", "300"), (f"{anio}-01-15", "80")):
        assert client.post(f"{API}/actividades", json={
            "nombre": "Venta", "grupo_encargado": "Grupo", "fecha": fecha,
            "inversion": "0", "ingresos_brutos": ingresos,
        }).status_code == 201

    actual = client.get(f"{API}/finanzas/liquidacion-anual").json()
    assert actual["anio"] == anio
    assert actual["anios_disponibles"][:2] == [anio, anio - 1]
    item = actual["socios_liquidados"][0]
    assert Decimal(item["total_ahorrado"]) == 500
    assert Decimal(item["utilidad_ganada"]) == 80

    anterior = client.get(f"{API}/finanzas/liquidacion-anual?anio={anio - 1}").json()
    item = anterior["socios_liquidados"][0]
    # El aporte es de este año: el año anterior no tiene ahorro, así que nadie recibe utilidad.
    assert Decimal(item["total_ahorrado"]) == 0
    assert Decimal(anterior["total_utilidades_generadas"]) == 300
    assert Decimal(item["utilidad_ganada"]) == 0

    siguiente = client.get(f"{API}/finanzas/liquidacion-anual?anio={anio + 1}").json()
    assert Decimal(siguiente["total_ahorro_acumulado"]) == 0
    assert client.get(f"{API}/finanzas/liquidacion-anual?anio=1990").status_code == 422


def test_inactivo_con_saldo_recupera_ahorro_sin_utilidades(client, socio):
    otro = client.post(f"{API}/socios", json={
        "cedula": "5550001", "nombre": "Inactivo", "telefono": "3000000000",
        "residencia": "Calle", "aporte_mensual": "100",
    }).json()
    sin_saldo = client.post(f"{API}/socios", json={
        "cedula": "5550002", "nombre": "Inactivo sin saldo", "telefono": "3000000000",
        "residencia": "Calle", "aporte_mensual": "100",
    }).json()
    movement(client, socio["id"], "APORTE", 100)
    movement(client, otro["id"], "APORTE", 100)
    movement(client, socio["id"], "PAGO_MULTA", 10)
    assert client.post(f"{API}/actividades", json={
        "nombre": "Venta", "grupo_encargado": "Grupo", "fecha": hoy_colombia().isoformat(),
        "inversion": "0", "ingresos_brutos": "40",
    }).status_code == 201
    # Con ahorro no se puede eliminar; se marca inactivo editando el socio.
    assert client.delete(f"{API}/socios/{otro['id']}").status_code == 409
    assert client.put(f"{API}/socios/{otro['id']}", json={"is_active": False}).status_code == 200
    assert client.delete(f"{API}/socios/{sin_saldo['id']}").status_code == 200

    result = client.get(f"{API}/finanzas/liquidacion-anual").json()
    items = {i["socio_id"]: i for i in result["socios_liquidados"]}
    assert sin_saldo["id"] not in items
    assert items[otro["id"]]["activo"] is False
    assert Decimal(items[otro["id"]]["total_ahorrado"]) == 100
    assert Decimal(items[otro["id"]]["utilidad_ganada"]) == 0
    assert Decimal(items[otro["id"]]["bien_comun_asignado"]) == 0
    assert Decimal(items[socio["id"]]["utilidad_ganada"]) == 40
    assert Decimal(items[socio["id"]]["bien_comun_asignado"]) == 10
    assert Decimal(result["gran_total_a_entregar"]) == 250

    bien_comun = client.get(f"{API}/finanzas/bien-comun").json()
    assert [s["id"] for s in bien_comun["socios"]] == [socio["id"]]


def test_liquidacion_descuenta_deuda_al_cierre(client, socio):
    movement(client, socio["id"], "APORTE", 1000)
    movement(client, socio["id"], "MULTA", 30)
    assert client.post(f"{API}/prestamos", json={
        "socio_id": socio["id"], "monto_prestado": "400", "tasa_interes": "5", "numero_cuotas": 2,
    }).status_code == 201
    item = client.get(f"{API}/finanzas/liquidacion-anual").json()["socios_liquidados"][0]
    assert Decimal(item["deuda_prestamos"]) == 440
    assert Decimal(item["multas_pendientes"]) == 30
    assert Decimal(item["total_neto_entregar"]) == 530
