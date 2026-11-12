"""Regla de intereses 7 % / 10 % de préstamos."""
from datetime import timedelta
from decimal import Decimal

from app.services.prestamos_service import hoy_colombia, sumar_meses

API = "/api/v1"


def crear_prestamo(client, socio, meses_atras=2, monto="1000", cuotas=3, **extra):
    # Estas pruebas cubren la regla anterior 7 % / 10 %, que sigue vigente en los
    # préstamos creados con ella; los préstamos nuevos usan REPARTO_7_3.
    extra.setdefault("regla_interes", "MORA_7_10")
    fecha = sumar_meses(hoy_colombia(), -meses_atras)
    response = client.post(f"{API}/prestamos", json={
        "socio_id": socio["id"], "monto_prestado": monto, "numero_cuotas": cuotas,
        "fecha_prestamo": fecha.isoformat(), **extra,
    })
    assert response.status_code == 201, response.text
    return response.json()


def abonar(client, pid, monto, fecha, **extra):
    return client.post(f"{API}/prestamos/{pid}/abonos", json={
        "prestamo_id": pid, "monto_abonado": str(monto), "fecha_pago": fecha.isoformat(), **extra,
    })


def test_prestamo_con_regla_7_10_explicita(client, socio):
    prestamo = crear_prestamo(client, socio, meses_atras=0, tasa_interes="5")
    assert prestamo["regla_interes"] == "MORA_7_10"
    assert Decimal(prestamo["tasa_interes"]) == 7
    assert Decimal(prestamo["tasa_mora"]) == 10
    assert Decimal(prestamo["total_intereses"]) == 210
    assert [p["numero_cuota"] for p in prestamo["periodos"]] == [1, 2, 3]


def test_prestamo_fijo_conserva_su_tasa(client, socio):
    prestamo = crear_prestamo(client, socio, meses_atras=0, tasa_interes="5", regla_interes="FIJA")
    assert prestamo["regla_interes"] == "FIJA"
    assert Decimal(prestamo["tasa_interes"]) == 5
    assert prestamo["periodos"] == []
    assert Decimal(prestamo["total_intereses"]) == 150


def test_vista_previa_sugiere_7_en_fecha_limite_y_10_al_dia_siguiente(client, socio):
    prestamo = crear_prestamo(client, socio)
    limite = sumar_meses(hoy_colombia(), -1)
    a_tiempo = client.get(f"{API}/prestamos/{prestamo['id']}/abonos/vista-previa",
                          params={"fecha_pago": limite.isoformat()}).json()
    assert a_tiempo["numero_cuota"] == 1
    assert a_tiempo["fecha_limite"] == limite.isoformat()
    assert Decimal(a_tiempo["tasa_sugerida"]) == 7 and a_tiempo["dias_retraso"] == 0
    assert Decimal(a_tiempo["pendiente_tasa_normal"]) == 70
    assert Decimal(a_tiempo["pendiente_tasa_mora"]) == 100
    assert a_tiempo["destino"] == "AHORRO_PERSONAL"

    tarde = client.get(f"{API}/prestamos/{prestamo['id']}/abonos/vista-previa",
                       params={"fecha_pago": (limite + timedelta(days=1)).isoformat()}).json()
    assert Decimal(tarde["tasa_sugerida"]) == 10 and tarde["dias_retraso"] == 1
    assert "1 día de retraso" in tarde["motivo"]


def test_abono_aplica_tasa_sugerida_o_la_elegida(client, socio):
    prestamo = crear_prestamo(client, socio)
    pid = prestamo["id"]
    limite1 = sumar_meses(hoy_colombia(), -1)

    # Sin tasa: a tiempo -> 7 %.
    ab = abonar(client, pid, 70, limite1, monto_capital="0", monto_interes="70")
    assert ab.status_code == 201, ab.text
    assert Decimal(ab.json()["tasa_aplicada"]) == 7 and ab.json()["dias_retraso"] == 0
    assert ab.json()["fecha_limite"] == limite1.isoformat()

    # Cuota 2 vence hoy; pagada un día "tarde" no es posible (sería futuro), así que
    # se prueba la cuota 2 con la tasa de mora elegida por el administrador.
    ab2 = abonar(client, pid, 100, hoy_colombia(), monto_capital="0", monto_interes="100", tasa_aplicada="10")
    assert ab2.status_code == 201, ab2.text
    assert ab2.json()["numero_cuota"] == 2 and Decimal(ab2.json()["tasa_aplicada"]) == 10

    detalle = client.get(f"{API}/prestamos/{pid}").json()
    tasas = {p["numero_cuota"]: (Decimal(p["tasa"]), p["estado"]) for p in detalle["periodos"]}
    assert tasas[1] == (7, "PAGADO") and tasas[2] == (10, "PAGADO")
    assert detalle["cuotas_pagadas"] == 2


def test_pago_tardio_con_tasa_7_elegida_por_el_administrador(client, socio):
    prestamo = crear_prestamo(client, socio)
    tarde = sumar_meses(hoy_colombia(), -1) + timedelta(days=3)
    ab = abonar(client, prestamo["id"], 70, tarde, monto_capital="0", monto_interes="70", tasa_aplicada="7")
    assert ab.status_code == 201, ab.text
    assert Decimal(ab.json()["tasa_aplicada"]) == 7 and ab.json()["dias_retraso"] == 3
    periodo = client.get(f"{API}/prestamos/{prestamo['id']}").json()["periodos"][0]
    assert Decimal(periodo["tasa"]) == 7 and Decimal(periodo["pendiente"]) == 0


def test_mes_vencido_sin_pagar_pasa_a_10_y_queda_en_mora(client, socio):
    prestamo = crear_prestamo(client, socio)
    detalle = client.get(f"{API}/prestamos/{prestamo['id']}").json()
    assert detalle["estado"] == "EN_MORA"
    assert Decimal(detalle["periodos"][0]["tasa"]) == 10
    assert Decimal(detalle["intereses_pendientes"]) == 100
    # Cuota 1 al 10 %, cuotas 2 (vence hoy) y 3 proyectadas al 7 %.
    assert Decimal(detalle["total_intereses"]) == 240
    assert Decimal(detalle["tasa_vigente"]) == 10


def test_validaciones_de_tasa_e_interes(client, socio):
    prestamo = crear_prestamo(client, socio)
    fecha = sumar_meses(hoy_colombia(), -1)
    otra_tasa = abonar(client, prestamo["id"], 80, fecha, monto_capital="0", monto_interes="80", tasa_aplicada="8")
    assert otra_tasa.status_code == 422
    excede = abonar(client, prestamo["id"], 90, fecha, monto_capital="0", monto_interes="90", tasa_aplicada="7")
    assert excede.status_code == 422
    assert "Registra los demás meses" in excede.json()["detail"]


def test_abono_sin_desglose_cubre_interes_y_luego_capital(client, socio):
    prestamo = crear_prestamo(client, socio)
    ab = abonar(client, prestamo["id"], 300, sumar_meses(hoy_colombia(), -1))
    assert ab.status_code == 201, ab.text
    assert Decimal(ab.json()["monto_interes"]) == 70
    assert Decimal(ab.json()["monto_capital"]) == 230


def test_editar_abono_recalcula_tasa(client, socio):
    prestamo = crear_prestamo(client, socio)
    limite = sumar_meses(hoy_colombia(), -1)
    ab = abonar(client, prestamo["id"], 70, limite, monto_capital="0", monto_interes="70").json()
    edit = client.put(f"{API}/prestamos/{prestamo['id']}/abonos/{ab['id']}", json={
        "prestamo_id": prestamo["id"], "monto_abonado": "100", "monto_capital": "0", "monto_interes": "100",
        "fecha_pago": (limite + timedelta(days=2)).isoformat(), "tasa_aplicada": "10",
    })
    assert edit.status_code == 200, edit.text
    assert Decimal(edit.json()["tasa_aplicada"]) == 10 and edit.json()["dias_retraso"] == 2


def test_bien_comun_desde_cuarta_cuota_con_regla_7_10(client, socio):
    prestamo = crear_prestamo(client, socio, meses_atras=5, cuotas=5)
    for indice in range(1, 6):
        fecha = sumar_meses(hoy_colombia(), -5 + indice)
        r = abonar(client, prestamo["id"], 70, fecha, monto_capital="0", monto_interes="70", numero_cuota=indice)
        assert r.status_code == 201, r.text
    bien_comun = client.get(f"{API}/finanzas/bien-comun").json()
    assert Decimal(bien_comun["total_intereses_obtenidos"]) == 350
    assert Decimal(bien_comun["total_dinero_total"]) == 140


def test_abono_puede_tener_fecha_anterior_al_prestamo(client, socio):
    # Las cuentas se pasan del cuaderno: un préstamo registrado hoy acepta abonos de días anteriores.
    prestamo = crear_prestamo(client, socio, meses_atras=0)
    ayer = hoy_colombia() - timedelta(days=1)
    ab = abonar(client, prestamo["id"], 70, ayer, monto_capital="0", monto_interes="70")
    assert ab.status_code == 201, ab.text
    assert ab.json()["fecha_pago"].startswith(ayer.isoformat())
    assert Decimal(ab.json()["tasa_aplicada"]) == 7
    # Los abonos aceptan también fechas futuras (se guarda la fecha elegida).
    manana_abono = hoy_colombia() + timedelta(days=1)
    futura = abonar(client, prestamo["id"], 10, manana_abono)
    assert futura.status_code == 201, futura.text
    assert futura.json()["fecha_pago"].startswith(manana_abono.isoformat())


def test_fecha_posterior_a_la_ultima_cuota_crea_la_siguiente(client, socio):
    # 4 cuotas desde hace 4 meses: la última (#4) vence hoy.
    prestamo = crear_prestamo(client, socio, meses_atras=4, monto="1000", cuotas=4)
    pid = prestamo["id"]
    hoy = hoy_colombia()
    for cuota in (1, 2, 3, 4):
        r = abonar(client, pid, 100, hoy, numero_cuota=cuota, monto_interes="100", monto_capital="0", tasa_aplicada="10")
        assert r.status_code == 201, r.text

    # Con todas las cuotas pagadas se propone la #5 aunque la fecha esté en plazo.
    previa = client.get(f"{API}/prestamos/{pid}/abonos/vista-previa", params={"fecha_pago": hoy.isoformat()}).json()
    assert previa["cuotas_disponibles"] == [1, 2, 3, 4, 5] and previa["cuota_nueva"] == 5

    # Un día después se crea la #5 con su fecha límite y queda seleccionada.
    fecha = hoy + timedelta(days=1)
    previa = client.get(f"{API}/prestamos/{pid}/abonos/vista-previa", params={"fecha_pago": fecha.isoformat()}).json()
    assert previa["cuotas_disponibles"] == [1, 2, 3, 4, 5]
    assert previa["cuota_nueva"] == 5 and previa["numero_cuota"] == 5
    nueva = previa["cuotas"][-1]
    assert nueva["nueva"] and nueva["fecha_limite"] == sumar_meses(sumar_meses(hoy, -4), 5).isoformat()

    # Una fecha muy posterior solo agrega la siguiente (#5), no salta números.
    lejana = hoy + timedelta(days=200)
    previa = client.get(f"{API}/prestamos/{pid}/abonos/vista-previa", params={"fecha_pago": lejana.isoformat()}).json()
    assert previa["cuotas_disponibles"] == [1, 2, 3, 4, 5]

    # Al guardar, el abono queda en la #5 y la siguiente fecha posterior propone la #6.
    r = abonar(client, pid, 70, fecha, monto_interes="70", monto_capital="0")
    assert r.status_code == 201, r.text
    assert r.json()["numero_cuota"] == 5
    detalle = client.get(f"{API}/prestamos/{pid}").json()
    assert [p["numero_cuota"] for p in detalle["periodos"]] == [1, 2, 3, 4, 5]
    assert Decimal(detalle["total_intereses"]) == 470
    siguiente = sumar_meses(sumar_meses(hoy, -4), 5) + timedelta(days=1)
    previa = client.get(f"{API}/prestamos/{pid}/abonos/vista-previa", params={"fecha_pago": siguiente.isoformat()}).json()
    assert previa["cuota_nueva"] == 6


def test_sin_capital_pendiente_no_se_crea_cuota_nueva(client, socio):
    prestamo = crear_prestamo(client, socio, meses_atras=1, monto="1000", cuotas=1)
    pid = prestamo["id"]
    hoy = hoy_colombia()
    r = abonar(client, pid, 1070, hoy, numero_cuota=1, monto_interes="70", monto_capital="1000", tasa_aplicada="7")
    assert r.status_code == 201, r.text
    assert client.get(f"{API}/prestamos/{pid}").json()["estado"] == "PAGADO"
    previa = client.get(f"{API}/prestamos/{pid}/abonos/vista-previa",
                        params={"fecha_pago": (hoy + timedelta(days=60)).isoformat()}).json()
    assert previa["cuota_nueva"] is None and previa["cuotas_disponibles"] == [1]


def _historial_de(client, entidad_tipo, entidad_id, accion):
    datos = client.get(f"{API}/historial", params={"limit": 50}).json()
    lista = datos if isinstance(datos, list) else datos.get("items", [])
    return next(i for i in lista if i["entidad_tipo"] == entidad_tipo and i["entidad_id"] == entidad_id and i["tipo_accion"] == accion)


def test_con_cuotas_pagadas_la_linea_nueva_cobra_el_mes_completo(client, socio):
    # 2 cuotas pactadas y pagadas al 7 %; la fecha sigue dentro de la cuota #2.
    prestamo = crear_prestamo(client, socio, meses_atras=1, monto="400000", cuotas=2)
    pid = prestamo["id"]
    hoy = hoy_colombia()
    for cuota in (1, 2):
        r = abonar(client, pid, 28000, hoy, numero_cuota=cuota, monto_interes="28000", monto_capital="0", tasa_aplicada="7")
        assert r.status_code == 201, r.text

    previa = client.get(f"{API}/prestamos/{pid}/abonos/vista-previa", params={"fecha_pago": hoy.isoformat()}).json()
    # No se cobra la diferencia 7 % → 10 % de la cuota #2: se crea la #3 con el mes completo.
    assert previa["cuota_nueva"] == 3 and previa["numero_cuota"] == 3
    assert Decimal(previa["pendiente_tasa_normal"]) == 28000
    assert Decimal(previa["pendiente_tasa_mora"]) == 40000

    r = abonar(client, pid, 140000, hoy, monto_interes="40000", monto_capital="100000", tasa_aplicada="10")
    assert r.status_code == 201, r.text
    assert r.json()["numero_cuota"] == 3
    detalle = client.get(f"{API}/prestamos/{pid}").json()
    assert Decimal(detalle["total_intereses"]) == 96000
    assert Decimal(detalle["saldo_pendiente"]) == 300000


def test_revertir_abono_creado_con_fecha_y_tasa(client, socio):
    prestamo = crear_prestamo(client, socio, meses_atras=1, monto="400000", cuotas=2)
    pid = prestamo["id"]
    hoy = hoy_colombia()
    r = abonar(client, pid, 128000, hoy, numero_cuota=1, monto_interes="28000", monto_capital="100000", tasa_aplicada="7")
    assert r.status_code == 201, r.text
    item = _historial_de(client, "AbonoPrestamo", r.json()["id"], "CREAR")
    revertido = client.post(f"{API}/historial/{item['id']}/revertir")
    assert revertido.status_code == 200, revertido.text
    detalle = client.get(f"{API}/prestamos/{pid}").json()
    assert detalle["abonos"] == [] and Decimal(detalle["saldo_pendiente"]) == 400000


def test_revertir_edicion_de_abono_restaura_la_tasa(client, socio):
    prestamo = crear_prestamo(client, socio, meses_atras=1, monto="400000", cuotas=2)
    pid = prestamo["id"]
    hoy = hoy_colombia()
    r = abonar(client, pid, 28000, hoy, numero_cuota=1, monto_interes="28000", monto_capital="0", tasa_aplicada="7")
    aid = r.json()["id"]
    editado = client.put(f"{API}/prestamos/{pid}/abonos/{aid}", json={
        "prestamo_id": pid, "monto_abonado": "40000", "monto_capital": "0", "monto_interes": "40000",
        "numero_cuota": 1, "fecha_pago": hoy.isoformat(), "tasa_aplicada": "10",
    })
    assert editado.status_code == 200, editado.text
    assert Decimal(editado.json()["tasa_aplicada"]) == 10
    item = _historial_de(client, "AbonoPrestamo", aid, "EDITAR")
    revertido = client.post(f"{API}/historial/{item['id']}/revertir")
    assert revertido.status_code == 200, revertido.text
    abono = client.get(f"{API}/prestamos/{pid}").json()["abonos"][0]
    assert Decimal(abono["monto_interes"]) == 28000 and Decimal(abono["tasa_aplicada"]) == 7
