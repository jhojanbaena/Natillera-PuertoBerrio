"""Aportes mensuales por mes y pago individual de multas (menú del socio)."""
API = "/api/v1"


def _mov(client, sid, **payload):
    return client.post(f"{API}/socios/{sid}/movimientos", json=payload)


def test_aporte_mensual_no_se_registra_dos_veces(client, socio):
    sid = socio["id"]
    datos = {"tipo_movimiento": "APORTE", "monto": "100.00", "periodo": "2026-03",
             "descripcion": "Aporte mensual — Marzo 2026", "fecha": "2026-03-05"}
    primero = _mov(client, sid, **datos)
    assert primero.status_code == 201, primero.text
    assert primero.json()["periodo"] == "2026-03"
    assert _mov(client, sid, **datos).status_code == 409

    # Otro mes sí se puede registrar, con su propio valor.
    assert _mov(client, sid, **{**datos, "periodo": "2026-04", "monto": "150.00"}).status_code == 201
    perfil = client.get(f"{API}/socios/{sid}/perfil").json()
    aportes = [m for m in perfil["historial_finanzas"] if m["tipo_movimiento"] == "APORTE"]
    assert sorted(m["periodo"] for m in aportes) == ["2026-03", "2026-04"]
    assert float(perfil["total_ahorrado"]) == 250.0


def test_periodo_invalido_o_en_otro_tipo(client, socio):
    sid = socio["id"]
    assert _mov(client, sid, tipo_movimiento="APORTE", monto="10", periodo="2026-13").status_code == 422
    assert _mov(client, sid, tipo_movimiento="MULTA", monto="10", periodo="2026-01").status_code == 422


def test_pago_de_multa_individual(client, socio):
    sid = socio["id"]
    multa = _mov(client, sid, tipo_movimiento="MULTA", monto="20.00", descripcion="Llegada tarde").json()
    perfil = client.get(f"{API}/socios/{sid}/perfil").json()
    assert perfil["multas"][0]["pagada"] is False

    # Monto distinto al de la multa: rechazado.
    assert _mov(client, sid, tipo_movimiento="PAGO_MULTA", monto="5", multa_id=multa["id"]).status_code == 422
    pago = _mov(client, sid, tipo_movimiento="PAGO_MULTA", monto="20.00", multa_id=multa["id"])
    assert pago.status_code == 201, pago.text
    # Segundo pago de la misma multa: rechazado.
    assert _mov(client, sid, tipo_movimiento="PAGO_MULTA", monto="20.00", multa_id=multa["id"]).status_code == 409

    perfil = client.get(f"{API}/socios/{sid}/perfil").json()
    assert perfil["multas"][0]["pagada"] is True
    assert perfil["multas"][0]["pago_id"] == pago.json()["id"]
    assert float(perfil["total_multas_pendientes"]) == 0


def test_editar_multa_pendiente_y_bloquear_pagada(client, socio):
    sid = socio["id"]
    multa = _mov(client, sid, tipo_movimiento="MULTA", monto="20.00", descripcion="Inasistencia").json()
    editada = client.put(f"{API}/socios/{sid}/multas/{multa['id']}", json={"monto": "15.00", "descripcion": "Inasistencia reunión"})
    assert editada.status_code == 200, editada.text
    assert float(editada.json()["monto"]) == 15.0
    assert float(client.get(f"{API}/socios/{sid}/perfil").json()["total_multas_pendientes"]) == 15.0

    assert _mov(client, sid, tipo_movimiento="PAGO_MULTA", monto="15.00", multa_id=multa["id"]).status_code == 201
    assert client.put(f"{API}/socios/{sid}/multas/{multa['id']}", json={"monto": "1.00"}).status_code == 409


def test_pagos_antiguos_sin_multa_cubren_las_mas_antiguas(client, socio):
    sid = socio["id"]
    m1 = _mov(client, sid, tipo_movimiento="MULTA", monto="10.00", fecha="2026-01-10").json()
    m2 = _mov(client, sid, tipo_movimiento="MULTA", monto="10.00", fecha="2026-02-10").json()
    # Pago registrado como antes, sin indicar la multa.
    assert _mov(client, sid, tipo_movimiento="PAGO_MULTA", monto="10.00").status_code == 201

    estados = {m["id"]: m["pagada"] for m in client.get(f"{API}/socios/{sid}/perfil").json()["multas"]}
    assert estados == {m1["id"]: True, m2["id"]: False}
    assert _mov(client, sid, tipo_movimiento="PAGO_MULTA", monto="10.00", multa_id=m1["id"]).status_code == 409
    assert _mov(client, sid, tipo_movimiento="PAGO_MULTA", monto="10.00", multa_id=m2["id"]).status_code == 201


def test_multa_de_otro_socio_no_se_puede_pagar(client, socio):
    otro = client.post(f"{API}/socios", json={
        "cedula": "987654321", "nombre": "Otro Socio", "telefono": "3009999999",
        "residencia": "Otra calle 1", "aporte_mensual": "130000.00",
    }).json()
    multa = _mov(client, otro["id"], tipo_movimiento="MULTA", monto="10.00").json()
    assert _mov(client, socio["id"], tipo_movimiento="PAGO_MULTA", monto="10.00", multa_id=multa["id"]).status_code == 404


def test_revertir_multa_con_pago_exige_revertir_pago_primero(client, socio):
    sid = socio["id"]
    multa = _mov(client, sid, tipo_movimiento="MULTA", monto="10.00").json()
    assert _mov(client, sid, tipo_movimiento="PAGO_MULTA", monto="10.00", multa_id=multa["id"]).status_code == 201
    historial = client.get(f"{API}/historial", params={"limit": 50}).json()
    items = historial["items"] if isinstance(historial, dict) else historial
    crear_multa = next(h for h in items if h["entidad_tipo"] == "FinanzaSocio" and h["entidad_id"] == multa["id"])
    assert client.post(f"{API}/historial/{crear_multa['id']}/revertir").status_code == 409


def test_socio_con_ahorro_no_se_puede_eliminar(client, socio):
    sid = socio["id"]
    assert _mov(client, sid, tipo_movimiento="APORTE", monto="100.00").status_code == 201
    for url in (f"{API}/socios/{sid}", f"{API}/socios/{sid}?hard_delete=true"):
        respuesta = client.delete(url)
        assert respuesta.status_code == 409
        assert "ahorrados" in respuesta.json()["detail"]
    assert client.get(f"{API}/socios/{sid}").json()["is_active"] is True

    # Sin ahorro (todo retirado) sí se puede.
    assert _mov(client, sid, tipo_movimiento="RETIRO_AHORRO", monto="100.00").status_code == 201
    assert client.delete(f"{API}/socios/{sid}").status_code == 200


def test_socio_solo_con_multas_se_puede_eliminar(client, socio):
    assert _mov(client, socio["id"], tipo_movimiento="MULTA", monto="10.00").status_code == 201
    assert client.delete(f"{API}/socios/{socio['id']}").status_code == 200


def _otro_socio(client, cedula="987654321", socio_id=None):
    datos = {"cedula": cedula, "nombre": "Otro Socio", "telefono": "3009999999",
             "residencia": "Otra calle 1", "aporte_mensual": "130000.00"}
    if socio_id:
        datos["id"] = socio_id
    return client.post(f"{API}/socios", json=datos).json()


def test_editar_cedula_del_socio(client, socio):
    sid = socio["id"]
    respuesta = client.put(f"{API}/socios/{sid}", json={"cedula": "111222333"})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["cedula"] == "111222333"
    _otro_socio(client)
    assert client.put(f"{API}/socios/{sid}", json={"cedula": "987654321"}).status_code == 400


def test_cambiar_id_mueve_aportes_multas_y_prestamos(client, socio, prestamo):
    sid = socio["id"]
    assert _mov(client, sid, tipo_movimiento="APORTE", monto="100.00", periodo="2026-01").status_code == 201
    multa = _mov(client, sid, tipo_movimiento="MULTA", monto="10.00").json()
    assert _mov(client, sid, tipo_movimiento="PAGO_MULTA", monto="10.00", multa_id=multa["id"]).status_code == 201
    antes = client.get(f"{API}/socios/{sid}/perfil").json()

    respuesta = client.put(f"{API}/socios/{sid}", json={"id": 50, "cedula": "555666777", "nombre": "Socio Movido"})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["id"] == 50 and respuesta.json()["cedula"] == "555666777"

    assert client.get(f"{API}/socios/{sid}").status_code == 404
    despues = client.get(f"{API}/socios/50/perfil").json()
    assert despues["total_ahorrado"] == antes["total_ahorrado"]
    assert len(despues["historial_finanzas"]) == len(antes["historial_finanzas"])
    assert all(m["socio_id"] == 50 for m in despues["historial_finanzas"])
    assert [p["id"] for p in despues["prestamos"]] == [prestamo["id"]]
    assert despues["multas"][0]["pagada"] is True
    assert client.get(f"{API}/prestamos/{prestamo['id']}").json()["socio_id"] == 50


def test_cambiar_id_a_uno_ocupado_no_cambia_nada(client, socio):
    otro = _otro_socio(client, socio_id=77)
    respuesta = client.put(f"{API}/socios/{socio['id']}", json={"id": otro["id"], "nombre": "No debe guardarse"})
    assert respuesta.status_code == 400
    assert client.get(f"{API}/socios/{socio['id']}").json()["nombre"] == socio["nombre"]


def test_revertir_cambio_de_id_devuelve_el_id_anterior(client, socio):
    sid = socio["id"]
    assert _mov(client, sid, tipo_movimiento="APORTE", monto="100.00").status_code == 201
    assert client.put(f"{API}/socios/{sid}", json={"id": 60, "cedula": "444555666"}).status_code == 200
    log = client.get(f"{API}/historial?tipo_accion=EDITAR").json()[0]
    assert client.post(f"{API}/historial/{log['id']}/revertir").status_code == 200, "revertir"
    restaurado = client.get(f"{API}/socios/{sid}/perfil").json()
    assert restaurado["cedula"] == socio["cedula"]
    assert float(restaurado["total_ahorrado"]) == 100.0
    assert client.get(f"{API}/socios/60").status_code == 404
