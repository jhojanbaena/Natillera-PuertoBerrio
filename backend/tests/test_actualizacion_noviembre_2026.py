"""Actualización: valor por unidad en actividades, historial del ojito, Total a recibir,
concepto de cada movimiento en Estadísticas e intereses cobrados vs. pendientes en Bien Común."""
from decimal import Decimal

from app.services.prestamos_service import hoy_colombia, sumar_meses

API = "/api/v1"
D = lambda v: Decimal(str(v))  # noqa: E731


def perfil(client, socio_id):
    r = client.get(f"{API}/socios/{socio_id}/perfil")
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- Actividades

def test_valor_por_unidad_calcula_la_ganancia_en_el_servidor(client, socio):
    sid = socio["id"]
    # Venta de empanadas: $3.000 x 20 = $60.000 (la ganancia enviada se ignora).
    r = client.post(f"{API}/socios/{sid}/actividades", json={
        "tipo": "OTRA", "nombre": "Venta de empanadas", "valor_unidad": "3000", "cantidad_vendida": 20, "ganancia": "1",
    })
    assert r.status_code == 201, r.text
    act = r.json()
    assert D(act["valor_unidad"]) == 3000 and act["cantidad_vendida"] == 20 and D(act["ganancia"]) == 60000

    # Editar la cantidad o el valor recalcula la ganancia.
    r = client.put(f"{API}/socios/{sid}/actividades/{act['id']}", json={
        "tipo": "OTRA", "nombre": "Venta de empanadas", "valor_unidad": "3500", "cantidad_vendida": 30, "ganancia": "0",
    })
    assert r.status_code == 200, r.text
    assert D(r.json()["ganancia"]) == 105000

    # Persiste: el perfil y la hoja traen el valor guardado.
    p = perfil(client, sid)
    assert D(p["actividades"][0]["ganancia"]) == 105000 and D(p["actividades"][0]["valor_unidad"]) == 3500
    hoja = client.get(f"{API}/socios/{sid}/hoja-ahorro").json()
    assert D(hoja["actividades"][0]["valor_unidad"]) == 3500
    assert D(p["total_ahorrado_socio"]["ganancias_actividades"]) == 105000


def test_valor_por_unidad_exige_cantidad(client, socio):
    r = client.post(f"{API}/socios/{socio['id']}/actividades", json={
        "tipo": "OTRA", "nombre": "Kits", "valor_unidad": "5000", "ganancia": "0",
    })
    assert r.status_code == 422


def test_rifa_interna_conserva_su_funcionamiento(client, socio):
    r = client.post(f"{API}/socios/{socio['id']}/actividades", json={
        "tipo": "RIFA_INTERNA", "mes": 3, "valor_unidad": "1000", "cantidad_vendida": 10, "ganancia": "39130",
    })
    assert r.status_code == 201, r.text
    act = r.json()
    # La ganancia de la rifa interna se escribe a mano: no se multiplica ni guarda valor por unidad.
    assert D(act["ganancia"]) == 39130 and act["valor_unidad"] is None


def test_actividades_sin_valor_por_unidad_siguen_igual(client, socio):
    r = client.post(f"{API}/socios/{socio['id']}/actividades", json={"nombre": "Costillas", "cantidad_vendida": 10, "ganancia": "20000"})
    assert r.status_code == 201, r.text
    assert D(r.json()["ganancia"]) == 20000 and r.json()["valor_unidad"] is None


# ---------------------------------------------------------------- Historial del ojito

def test_operaciones_del_ojito_quedan_en_el_historial_del_socio(client, socio):
    sid = socio["id"]
    act = client.post(f"{API}/socios/{sid}/actividades", json={
        "nombre": "Empanadas", "valor_unidad": "3000", "cantidad_vendida": 20, "ganancia": "0",
    }).json()
    client.put(f"{API}/socios/{sid}/actividades/{act['id']}", json={
        "nombre": "Empanadas", "valor_unidad": "3000", "cantidad_vendida": 25, "ganancia": "0",
    })
    # Guardar sin cambios no genera un registro duplicado.
    client.put(f"{API}/socios/{sid}/actividades/{act['id']}", json={
        "nombre": "Empanadas", "valor_unidad": "3000", "cantidad_vendida": 25, "ganancia": "0",
    })
    client.delete(f"{API}/socios/{sid}/actividades/{act['id']}")

    multa = client.post(f"{API}/socios/{sid}/movimientos", json={
        "tipo_movimiento": "MULTA", "monto": "5000", "descripcion": "Llegada tarde",
    }).json()
    r = client.put(f"{API}/socios/{sid}/multas/{multa['id']}", json={"monto": "8000", "descripcion": "Inasistencia"})
    assert r.status_code == 200, r.text

    p = perfil(client, sid)
    bitacora = p["movimientos_bitacora"]
    tipos = [m["tipo"] for m in bitacora]
    assert tipos == ["ACTIVIDAD_AGREGADA", "ACTIVIDAD_MODIFICADA", "ACTIVIDAD_ELIMINADA", "MULTA_MODIFICADA"]
    assert len({m["clave"] for m in bitacora}) == len(bitacora)
    assert all(m["fecha"] and m["usuario_nombre"] for m in bitacora)

    modificada = bitacora[1]
    cambios = {c["campo"]: (c["antes"], c["despues"]) for c in modificada["cambios"]}
    assert cambios == {"cantidad_vendida": ("20", "25"), "ganancia": ("$60.000", "$75.000")}

    multa_mod = {c["campo"]: (c["antes"], c["despues"]) for c in bitacora[3]["cambios"]}
    assert multa_mod == {"descripcion": ("Llegada tarde", "Inasistencia"), "monto": ("$5.000", "$8.000")}

    # La multa (vigente) sale una sola vez en historial_finanzas, con su registro de auditoría.
    assert [m["id"] for m in p["historial_finanzas"]] == [multa["id"]]
    assert p["auditoria_finanzas"][str(multa["id"])]["usuario_nombre"]


def test_bitacora_no_mezcla_socios(client, socio):
    otro = client.post(f"{API}/socios", json={
        "cedula": "987654321", "nombre": "Otra Socia", "telefono": "3009999999",
        "residencia": "Carrera 1", "aporte_mensual": "130000.00",
    }).json()
    client.post(f"{API}/socios/{otro['id']}/actividades", json={"nombre": "Kits", "ganancia": "10000"})
    assert perfil(client, socio["id"])["movimientos_bitacora"] == []
    assert len(perfil(client, otro["id"])["movimientos_bitacora"]) == 1


# ---------------------------------------------------------------- Total a recibir

def test_total_a_recibir_resta_deducciones_sin_prestamos(client, socio):
    sid = socio["id"]
    client.post(f"{API}/socios/{sid}/movimientos", json={"tipo_movimiento": "APORTE", "monto": "2000000"})
    client.post(f"{API}/socios/{sid}/movimientos", json={"tipo_movimiento": "MULTA", "monto": "350000"})
    client.post(f"{API}/prestamos", json={
        "socio_id": sid, "monto_prestado": "500000", "numero_cuotas": 4, "fecha_prestamo": hoy_colombia().isoformat(),
    })
    hoja = client.get(f"{API}/socios/{sid}/hoja-ahorro").json()
    total = D(hoja["total_ahorrado"]["total"])
    capital = next(D(f["valor"]) for f in hoja["deducciones"] if f["concepto"] == "Préstamos")
    assert capital == 500000
    # Deducciones a descontar: todas menos el capital del préstamo pendiente.
    assert D(hoja["deducciones_a_descontar"]) == D(hoja["total_deducciones"]) - capital == 350000
    assert D(hoja["total_a_recibir"]) == total - 350000


# ---------------------------------------------------------------- Estadísticas

def test_estadisticas_identifican_concepto_y_origen(client, socio):
    sid = socio["id"]
    client.post(f"{API}/socios/{sid}/movimientos", json={"tipo_movimiento": "APORTE", "monto": "100000"})
    client.post(f"{API}/socios/{sid}/actividades", json={"nombre": "Empanadas", "valor_unidad": "3000", "cantidad_vendida": 20, "ganancia": "0"})
    pr = client.post(f"{API}/prestamos", json={
        "socio_id": sid, "monto_prestado": "1000000", "numero_cuotas": 4, "fecha_prestamo": hoy_colombia().isoformat(),
    }).json()
    client.post(f"{API}/prestamos/{pr['id']}/abonos", json={
        "prestamo_id": pr["id"], "monto_abonado": "100000", "fecha_pago": hoy_colombia().isoformat(),
    })

    datos = client.get(f"{API}/estadisticas").json()
    movs = datos["movimientos"]
    # Un registro por movimiento real, sin duplicados ni omisiones.
    assert len(movs) == datos["totales"]["cantidad"]
    assert len({(m["tipo"], m["referencia"]) for m in movs}) == len(movs)
    por_tipo = {m["tipo"]: m for m in movs}
    assert por_tipo["APORTE"]["origen"] == "Socios" and "Socio Prueba" in por_tipo["APORTE"]["descripcion"]
    assert por_tipo["DESEMBOLSO_PRESTAMO"]["descripcion"].startswith(f"Préstamo #{pr['id']} entregado a Socio Prueba")
    assert por_tipo["INTERES_PRESTAMO"]["concepto"] == "Intereses de préstamos"
    assert "cuota #1" in por_tipo["INTERES_PRESTAMO"]["descripcion"]
    assert "Empanadas" in por_tipo["GANANCIA_ACTIVIDAD_SOCIO"]["descripcion"]
    assert D(por_tipo["GANANCIA_ACTIVIDAD_SOCIO"]["monto"]) == 60000
    # Cada periodo trae sus conceptos y suman lo mismo que el periodo.
    for periodo in datos["serie"]:
        ingresos = sum(D(t["total"]) for t in periodo["por_tipo"] if t["naturaleza"] == "INGRESO")
        assert ingresos == D(periodo["ingresos"])
    assert sum(D(m["monto"]) for m in movs if m["naturaleza"] == "INGRESO") == D(datos["totales"]["ingresos"])


# ---------------------------------------------------------------- Bien Común

def test_bien_comun_distingue_intereses_cobrados_y_pendientes(client, socio):
    sid = socio["id"]
    # Préstamo de hace 3 meses (regla 10 %: 7 % socio / 3 % bien común): 3 cuotas vencidas de $100.000.
    pr = client.post(f"{API}/prestamos", json={
        "socio_id": sid, "monto_prestado": "1000000", "numero_cuotas": 6,
        "fecha_prestamo": sumar_meses(hoy_colombia(), -3).isoformat(),
    }).json()
    antes = client.get(f"{API}/finanzas/bien-comun").json()
    assert D(antes["total_intereses_bien_comun"]) == 0
    assert D(antes["total_dinero_total"]) == 0
    pendiente_antes = D(antes["total_intereses_pendientes"])
    assert pendiente_antes > 0
    assert D(antes["total_intereses_pendientes_bien_comun"]) == (pendiente_antes * 3 / 10).quantize(Decimal("0.01"))

    # Se cobra la cuota #1: pasa de pendiente a cobrado, sin contarse dos veces.
    client.post(f"{API}/prestamos/{pr['id']}/abonos", json={
        "prestamo_id": pr["id"], "monto_abonado": "100000", "numero_cuota": 1, "fecha_pago": hoy_colombia().isoformat(),
    })
    despues = client.get(f"{API}/finanzas/bien-comun").json()
    assert D(despues["total_intereses_obtenidos"]) == 100000
    assert D(despues["total_intereses_bien_comun"]) == 30000
    assert D(despues["total_dinero_total"]) == 30000  # solo lo cobrado
    assert D(despues["total_intereses_pendientes"]) == pendiente_antes - 100000
    fila = next(f for f in despues["intereses_por_prestamo"] if f["prestamo_id"] == pr["id"])
    assert D(fila["intereses_cobrados_bien_comun"]) == 30000
    assert D(fila["intereses_pendientes"]) == pendiente_antes - 100000


# ---------------------------------------------------------------- Cuota mínima

def test_socio_nuevo_exige_cuota_minima_de_130000(client):
    base = {"cedula": "55555555", "nombre": "Socio Nuevo", "telefono": "3001112233", "residencia": "Calle 5"}
    assert client.post(f"{API}/socios", json={**base, "aporte_mensual": "129999.99"}).status_code == 422
    r = client.post(f"{API}/socios", json={**base, "aporte_mensual": "130000"})
    assert r.status_code == 201, r.text
