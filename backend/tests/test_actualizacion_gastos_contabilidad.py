"""Regla de intereses 10 % (7 % socio / 3 % bien común), abonos con cualquier fecha,
Gastos Generales en la liquidación y Contabilidad con registros inmutables."""
from datetime import date, timedelta
from decimal import Decimal

from app.services.prestamos_service import hoy_colombia, sumar_meses

API = "/api/v1"
D = Decimal


def crear_socio(client, cedula, nombre, aporte=None, fecha=None):
    r = client.post(f"{API}/socios", json={
        "cedula": cedula, "nombre": nombre, "telefono": "3000000000",
        "residencia": "Calle 1", "aporte_mensual": "100.00",
    })
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    if aporte:
        datos = {"tipo_movimiento": "APORTE", "monto": aporte}
        if fecha:
            datos["fecha"] = fecha
        r = client.post(f"{API}/socios/{sid}/movimientos", json=datos)
        assert r.status_code in (200, 201), r.text
    return sid


def abonar(client, pid, fecha, capital="0", interes="0", **extra):
    total = D(capital) + D(interes)
    return client.post(f"{API}/prestamos/{pid}/abonos", json={
        "prestamo_id": pid, "monto_abonado": str(total), "monto_capital": capital,
        "monto_interes": interes, "fecha_pago": fecha, **extra,
    })


def liquidacion(client, anio):
    r = client.get(f"{API}/finanzas/liquidacion-anual", params={"anio": anio})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- 1. Préstamos


def test_prestamo_nuevo_usa_10_por_ciento_repartido_7_socio_3_bien_comun(client, socio):
    hoy = hoy_colombia()
    r = client.post(f"{API}/prestamos", json={
        "socio_id": socio["id"], "monto_prestado": "1000000", "numero_cuotas": 3,
        "fecha_prestamo": hoy.isoformat(),
    })
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["regla_interes"] == "REPARTO_7_3"
    assert D(p["tasa_interes"]) == 10
    primero = p["periodos"][0]
    # Ejemplo del requerimiento: 1.000.000 -> 100.000 de interés = 70.000 socio + 30.000 bien común.
    assert D(primero["valor"]) == 100000
    assert D(primero["interes_socio"]) == 70000
    assert D(primero["interes_bien_comun"]) == 30000

    ab = abonar(client, p["id"], hoy.isoformat(), interes="100000", numero_cuota=1)
    assert ab.status_code == 201, ab.text
    assert D(ab.json()["interes_bien_comun"]) == 30000
    assert D(ab.json()["interes_socio"]) == 70000

    bien_comun = client.get(f"{API}/finanzas/bien-comun").json()
    assert D(bien_comun["total_intereses_obtenidos"]) == 100000
    assert D(bien_comun["total_dinero_total"]) == 30000  # solo el 3 %


def test_intereses_sobre_capital_pendiente_continuan_hasta_pagar_el_capital(client, socio):
    pid = client.post(f"{API}/prestamos", json={
        "socio_id": socio["id"], "monto_prestado": "1000000", "numero_cuotas": 2,
        "fecha_prestamo": "2025-01-15",
    }).json()["id"]
    # Abono a capital de 200.000 antes de iniciar el mes 2: el mes 2 se calcula sobre 800.000.
    assert abonar(client, pid, "2025-01-20", capital="200000").status_code == 201
    # Capital restante pagado el 2025-03-20: el mes 3 (fuera del plazo de 2 cuotas) ya había
    # iniciado el 2025-03-15 con 800.000 pendientes, así que también causa interés.
    assert abonar(client, pid, "2025-03-20", capital="800000").status_code == 201

    p = client.get(f"{API}/prestamos/{pid}").json()
    assert [(m["numero_cuota"], D(m["base"]), D(m["valor"])) for m in p["periodos"]] == [
        (1, 1000000, 100000), (2, 800000, 80000), (3, 800000, 80000),
    ]
    assert D(p["total_intereses"]) == 260000
    assert D(p["saldo_pendiente"]) == 0
    # El capital está pagado pero los intereses no: no queda PAGADO (son conceptos separados).
    assert p["estado"] == "EN_MORA"
    assert D(p["intereses_pendientes"]) == 260000

    for cuota, valor, fecha in ((1, "100000", "2025-02-10"), (2, "80000", "2025-03-10"), (3, "80000", "2025-04-10")):
        r = abonar(client, pid, fecha, interes=valor, numero_cuota=cuota)
        assert r.status_code == 201, r.text
    p = client.get(f"{API}/prestamos/{pid}").json()
    assert p["estado"] == "PAGADO"
    assert all(m["estado"] == "PAGADO" for m in p["periodos"])

    # Liquidación 2025: 30 % al bien común y 70 % al ahorro personal del socio.
    liq = liquidacion(client, 2025)
    assert D(liq["total_bien_comun_general"]) == 78000
    item = liq["socios_liquidados"][0]
    assert D(item["total_ahorrado"]) == 182000
    assert D(item["bien_comun_asignado"]) == 78000
    assert D(item["deuda_prestamos"]) == 0


def test_sin_abonos_los_meses_se_siguen_causando_mientras_haya_capital(client, socio):
    hoy = hoy_colombia()
    inicio = sumar_meses(hoy, -5)
    pid = client.post(f"{API}/prestamos", json={
        "socio_id": socio["id"], "monto_prestado": "500000", "numero_cuotas": 1,
        "fecha_prestamo": inicio.isoformat(),
    }).json()["id"]
    p = client.get(f"{API}/prestamos/{pid}").json()
    esperados = sum(1 for i in range(1, 50) if sumar_meses(inicio, i - 1) <= hoy)
    assert esperados >= 5
    assert len(p["periodos"]) == esperados
    assert D(p["total_intereses"]) == 50000 * esperados
    assert p["estado"] == "EN_MORA"
    # Un abono de capital solo cambia los meses que inician después de su fecha.
    abonar(client, pid, sumar_meses(inicio, 2).isoformat(), capital="100000")
    p = client.get(f"{API}/prestamos/{pid}").json()
    bases = [D(m["base"]) for m in p["periodos"]]
    assert bases[:2] == [500000, 500000] and all(b == 400000 for b in bases[2:])


def test_abono_acepta_fecha_pasada_actual_y_futura(client, socio):
    hoy = hoy_colombia()
    pid = client.post(f"{API}/prestamos", json={
        "socio_id": socio["id"], "monto_prestado": "1000000", "numero_cuotas": 6,
        "fecha_prestamo": sumar_meses(hoy, -1).isoformat(),
    }).json()["id"]
    for fecha in (hoy - timedelta(days=40), hoy, hoy + timedelta(days=20)):
        r = abonar(client, pid, fecha.isoformat(), capital="10000")
        assert r.status_code == 201, r.text
        assert r.json()["fecha_pago"].startswith(fecha.isoformat())
    detalle = client.get(f"{API}/prestamos/{pid}").json()
    fechas = sorted(a["fecha_pago"][:10] for a in detalle["abonos"])
    assert fechas == sorted(f.isoformat() for f in (hoy - timedelta(days=40), hoy, hoy + timedelta(days=20)))
    # Editar a una fecha futura también se guarda.
    abono_id = detalle["abonos"][0]["id"]
    futura = (hoy + timedelta(days=60)).isoformat()
    r = client.put(f"{API}/prestamos/{pid}/abonos/{abono_id}", json={
        "prestamo_id": pid, "monto_abonado": "10000", "monto_capital": "10000", "monto_interes": "0",
        "fecha_pago": futura,
    })
    assert r.status_code == 200, r.text
    assert r.json()["fecha_pago"].startswith(futura)


def test_fecha_posterior_a_la_ultima_cuota_agrega_la_siguiente(client, socio):
    hoy = hoy_colombia()
    # 2 cuotas pactadas: la última vence hoy + 1 mes; el mes 3 inicia ese día.
    pid = client.post(f"{API}/prestamos", json={
        "socio_id": socio["id"], "monto_prestado": "1000", "numero_cuotas": 2,
        "fecha_prestamo": sumar_meses(hoy, -1).isoformat(),
    }).json()["id"]
    for cuota in (1, 2):
        assert abonar(client, pid, hoy.isoformat(), interes="100", numero_cuota=cuota).status_code == 201
    previa = client.get(f"{API}/prestamos/{pid}/abonos/vista-previa", params={"fecha_pago": hoy.isoformat()}).json()
    # Con todas las cuotas pagadas ya se propone la siguiente, aunque la fecha esté en plazo.
    assert previa["cuotas_disponibles"] == [1, 2, 3] and previa["cuota_nueva"] == 3

    # Una fecha después de la última cuota agrega la cuota 3 y la propone sola.
    fecha = (sumar_meses(hoy, 1) + timedelta(days=1)).isoformat()
    previa = client.get(f"{API}/prestamos/{pid}/abonos/vista-previa", params={"fecha_pago": fecha}).json()
    assert previa["cuotas_disponibles"] == [1, 2, 3]
    assert previa["numero_cuota"] == 3 and D(previa["pendiente_tasa_normal"]) == 100

    r = abonar(client, pid, fecha, interes="100")
    assert r.status_code == 201, r.text
    assert r.json()["numero_cuota"] == 3
    detalle = client.get(f"{API}/prestamos/{pid}").json()
    assert D(detalle["total_intereses"]) == 300 and detalle["cuotas_pagadas"] == 3


def test_tasa_distinta_al_10_se_rechaza_en_regla_7_3(client, socio):
    hoy = hoy_colombia()
    pid = client.post(f"{API}/prestamos", json={
        "socio_id": socio["id"], "monto_prestado": "1000", "numero_cuotas": 2, "fecha_prestamo": hoy.isoformat(),
    }).json()["id"]
    r = abonar(client, pid, hoy.isoformat(), interes="70", tasa_aplicada="7")
    assert r.status_code == 422
    r = abonar(client, pid, hoy.isoformat(), interes="150", numero_cuota=1)
    assert r.status_code == 422  # supera el 10 % del mes


# ---------------------------------------------------------------- 2. Gastos generales


def test_gastos_generales_se_reparten_entre_socios_activos_y_se_descuentan(client):
    anio = hoy_colombia().year
    ids = [crear_socio(client, f"10{i}0000", f"Socio {i}", aporte="2000000") for i in range(4)]
    # Un socio inactivo no participa en los gastos.
    client.put(f"{API}/socios/{ids[3]}", json={"is_active": False})

    vacio = client.get(f"{API}/gastos-generales", params={"anio": anio}).json()
    assert D(vacio["total_gastos"]) == 0 and D(vacio["gasto_por_socio"]) == 0
    assert vacio["socios_activos"] == 3

    g1 = client.post(f"{API}/gastos-generales", json={"descripcion": "Papelería", "monto": "100000"})
    assert g1.status_code == 201, g1.text
    g2 = client.post(f"{API}/gastos-generales", json={"descripcion": "Transporte", "monto": "200000"})
    assert g2.status_code == 201
    resumen = client.get(f"{API}/gastos-generales", params={"anio": anio}).json()
    assert D(resumen["total_gastos"]) == 300000
    assert D(resumen["gasto_por_socio"]) == 100000
    assert [g["descripcion"] for g in resumen["gastos"]] == ["Papelería", "Transporte"]

    liq = liquidacion(client, anio)
    por_id = {s["socio_id"]: s for s in liq["socios_liquidados"]}
    for sid in ids[:3]:
        item = por_id[sid]
        assert D(item["liquidacion_antes_gastos"]) == 2000000
        assert D(item["gastos_generales"]) == 100000
        assert D(item["total_neto_entregar"]) == 1900000
    assert D(por_id[ids[3]]["gastos_generales"]) == 0
    assert D(por_id[ids[3]]["total_neto_entregar"]) == 2000000
    assert D(liq["total_gastos_descontados"]) == 300000  # se descuenta una sola vez en total

    # Editar y eliminar recalculan el descuento (no se acumula).
    assert client.put(f"{API}/gastos-generales/{g2.json()['id']}", json={"descripcion": "Transporte", "monto": "500000"}).status_code == 200
    assert client.delete(f"{API}/gastos-generales/{g1.json()['id']}").status_code == 200
    liq = liquidacion(client, anio)
    assert D(liq["total_gastos_descontados"]) == 500000
    assert {D(s["gastos_generales"]) for s in liq["socios_liquidados"] if s["activo"]} == {D("166666.67"), D("166666.66")}

    # Si cambia la cantidad de socios activos, el reparto se actualiza.
    client.put(f"{API}/socios/{ids[3]}", json={"is_active": True})
    resumen = client.get(f"{API}/gastos-generales", params={"anio": anio}).json()
    assert resumen["socios_activos"] == 4 and D(resumen["gasto_por_socio"]) == 125000
    liq = liquidacion(client, anio)
    assert all(D(s["gastos_generales"]) == 125000 for s in liq["socios_liquidados"])

    # El pago de la liquidación usa el neto con el descuento.
    r = client.post(f"{API}/finanzas/liquidacion-anual/pagos", json={"anio": anio, "socio_id": ids[0], "metodo_pago": "EFECTIVO"})
    assert r.status_code == 201, r.text
    assert D(r.json()["monto"]) == 1875000

    # Los gastos de otro año no afectan este año.
    client.post(f"{API}/gastos-generales", json={"descripcion": "Otro año", "monto": "999", "anio": anio - 1})
    assert D(liquidacion(client, anio)["total_gastos_descontados"]) == 500000


def test_gastos_sin_socios_activos_no_divide_entre_cero(client):
    sid = crear_socio(client, "5550000", "Único")
    client.put(f"{API}/socios/{sid}", json={"is_active": False})
    client.post(f"{API}/gastos-generales", json={"descripcion": "Materiales", "monto": "50000"})
    resumen = client.get(f"{API}/gastos-generales").json()
    assert resumen["socios_activos"] == 0 and D(resumen["gasto_por_socio"]) == 0
    assert liquidacion(client, hoy_colombia().year)["total_gastos_descontados"] in ("0", "0.00")


def test_gastos_validaciones_y_permisos(client):
    assert client.post(f"{API}/gastos-generales", json={"descripcion": "  ", "monto": "10"}).status_code == 422
    assert client.post(f"{API}/gastos-generales", json={"descripcion": "X", "monto": "-1"}).status_code == 422
    from app.core.security import create_access_token
    lector = {"Authorization": "Bearer " + create_access_token("reader-test")}
    assert client.post(f"{API}/gastos-generales", json={"descripcion": "X", "monto": "1"}, headers=lector).status_code == 403
    assert client.get(f"{API}/gastos-generales", headers=lector).status_code == 200


# ---------------------------------------------------------------- 3. Contabilidad


def test_contabilidad_compara_cuentas_con_dinero_del_sistema_y_conserva_registros(client):
    crear_socio(client, "7770000", "Ahorradora", aporte="10000000")
    actual = client.get(f"{API}/contabilidad").json()
    # Conectado a los registros: 10.000.000 aportados y nada prestado.
    assert D(actual["dinero_esperado"]) == 10000000
    assert D(actual["desglose"]["liquidez_sistema"]) == 10000000
    assert actual["cuentas"] == [] and D(actual["total_cuentas"]) == 0
    assert D(actual["diferencia"]) == -10000000 and actual["resultado"] == "FALTANTE"

    # No se puede guardar un registro sin cuentas.
    assert client.post(f"{API}/contabilidad/registros", json={}).status_code == 422

    banco = client.post(f"{API}/contabilidad/cuentas", json={"nombre": "Cuenta Bancaria", "valor": "6000000"}).json()
    efectivo = client.post(f"{API}/contabilidad/cuentas", json={"nombre": "Efectivo", "valor": "3500000"}).json()
    actual = client.get(f"{API}/contabilidad").json()
    assert D(actual["total_cuentas"]) == 9500000
    assert D(actual["diferencia"]) == -500000 and actual["resultado"] == "FALTANTE"

    r1 = client.post(f"{API}/contabilidad/registros", json={"observacion": "Arqueo 1"})
    assert r1.status_code == 201, r1.text
    reg1 = r1.json()
    assert reg1["resultado"] == "FALTANTE" and D(reg1["diferencia"]) == -500000
    assert [(c["nombre"], D(c["valor"])) for c in reg1["cuentas"]] == [("Cuenta Bancaria", 6000000), ("Efectivo", 3500000)]

    # Cuadrada.
    client.put(f"{API}/contabilidad/cuentas/{efectivo['id']}", json={"nombre": "Efectivo", "valor": "4000000"})
    assert client.get(f"{API}/contabilidad").json()["resultado"] == "CUADRADA"
    reg2 = client.post(f"{API}/contabilidad/registros", json={}).json()
    assert reg2["resultado"] == "CUADRADA" and D(reg2["diferencia"]) == 0

    # Sobrante.
    client.put(f"{API}/contabilidad/cuentas/{banco['id']}", json={"nombre": "Banco", "valor": "6200000"})
    actual = client.get(f"{API}/contabilidad").json()
    assert actual["resultado"] == "SOBRANTE" and D(actual["diferencia"]) == 200000

    # Borrar o editar cuentas actuales no cambia los registros guardados.
    client.delete(f"{API}/contabilidad/cuentas/{banco['id']}")
    guardado = client.get(f"{API}/contabilidad/registros/{reg1['id']}").json()
    assert guardado == reg1
    historial = client.get(f"{API}/contabilidad/registros").json()
    assert [h["id"] for h in historial] == [reg2["id"], reg1["id"]]


def test_contabilidad_descuenta_prestamos_gastos_y_liquidaciones(client, socio):
    anio = hoy_colombia().year
    client.post(f"{API}/socios/{socio['id']}/movimientos", json={"tipo_movimiento": "APORTE", "monto": "5000000"})
    client.post(f"{API}/prestamos", json={
        "socio_id": socio["id"], "monto_prestado": "1000000", "numero_cuotas": 2,
        "fecha_prestamo": hoy_colombia().isoformat(),
    })
    client.post(f"{API}/gastos-generales", json={"descripcion": "Papelería", "monto": "200000"})
    d = client.get(f"{API}/contabilidad").json()["desglose"]
    assert D(d["cartera_prestada"]) == 1000000
    assert D(d["dinero_esperado"]) == 5000000 - 1000000 - 200000
    assert D(d["liquidaciones_pagadas"]) == 0
    # Al pagar una liquidación ese dinero sale de caja.
    r = client.post(f"{API}/finanzas/liquidacion-anual/pagos", json={"anio": anio, "socio_id": socio["id"], "metodo_pago": "EFECTIVO"})
    assert r.status_code == 201, r.text
    pagado = D(r.json()["monto"])
    d2 = client.get(f"{API}/contabilidad").json()["desglose"]
    assert D(d2["liquidaciones_pagadas"]) == pagado
    assert D(d2["dinero_esperado"]) == D(d["dinero_esperado"]) - pagado
