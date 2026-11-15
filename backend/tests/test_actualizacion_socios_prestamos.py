"""Deducciones, Total ahorrado, historial de abonos del socio y regla del segundo préstamo."""
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.orm import sessionmaker

from app.models.prestamo import Prestamo
from app.services.prestamos_service import hoy_colombia, sumar_meses

API = "/api/v1"
D = lambda v: Decimal(str(v))  # noqa: E731


def crear_prestamo(client, socio_id, monto="1000000", cuotas=4, meses_atras=0, **extra):
    r = client.post(f"{API}/prestamos", json={
        "socio_id": socio_id, "monto_prestado": monto, "numero_cuotas": cuotas,
        "fecha_prestamo": sumar_meses(hoy_colombia(), -meses_atras).isoformat(), **extra,
    })
    assert r.status_code == 201, r.text
    return r.json()


def abonar(client, pid, monto, **extra):
    r = client.post(f"{API}/prestamos/{pid}/abonos", json={
        "prestamo_id": pid, "monto_abonado": str(monto), "fecha_pago": hoy_colombia().isoformat(), **extra,
    })
    assert r.status_code == 201, r.text
    return r.json()


def perfil(client, socio_id):
    r = client.get(f"{API}/socios/{socio_id}/perfil")
    assert r.status_code == 200, r.text
    return r.json()


def test_segundo_prestamo_lleva_todo_el_interes_al_bien_comun_desde_la_primera_cuota(client, socio):
    primero = crear_prestamo(client, socio["id"])
    assert primero["orden_socio"] == 1 and primero["es_segundo_prestamo"] is False
    assert client.get(f"{API}/prestamos/conteo/por-socio").json() == {str(socio["id"]): 1}

    # Aunque el primero esté pagado o no, el siguiente es el segundo préstamo.
    segundo = crear_prestamo(client, socio["id"])
    assert segundo["orden_socio"] == 2 and segundo["es_segundo_prestamo"] is True
    assert {p["destino"] for p in segundo["periodos"]} == {"BIEN_COMUN_SEGUNDO_PRESTAMO"}
    assert all(D(p["interes_socio"]) == 0 and D(p["interes_bien_comun"]) == D(p["valor"]) for p in segundo["periodos"])

    previa = client.get(f"{API}/prestamos/{segundo['id']}/abonos/vista-previa").json()
    assert previa["numero_cuota"] == 1
    assert D(previa["interes_bien_comun"]) == 100000 and D(previa["interes_socio"]) == 0

    # Cuota 1 del segundo préstamo: 100 % al bien común.
    ab2 = abonar(client, segundo["id"], 100000)
    assert ab2["numero_cuota"] == 1
    assert D(ab2["interes_bien_comun"]) == 100000 and D(ab2["interes_socio"]) == 0

    # El primer préstamo conserva su regla original 7 % / 3 %.
    ab1 = abonar(client, primero["id"], 100000)
    assert D(ab1["interes_bien_comun"]) == 30000 and D(ab1["interes_socio"]) == 70000

    bien_comun = client.get(f"{API}/finanzas/bien-comun").json()
    assert D(bien_comun["total_dinero_total"]) == 130000

    # El interés del segundo préstamo no suma al ahorro personal del socio.
    total = perfil(client, socio["id"])["total_ahorrado_socio"]
    assert D(total["ganancias_intereses"]) == 70000


def test_tercer_prestamo_tambien_va_al_bien_comun_y_editar_abono_conserva_la_regla(client, socio):
    crear_prestamo(client, socio["id"])
    crear_prestamo(client, socio["id"])
    tercero = crear_prestamo(client, socio["id"], regla_interes="FIJA", tasa_interes="5")
    assert tercero["orden_socio"] == 3 and tercero["es_segundo_prestamo"] is True
    ab = abonar(client, tercero["id"], 50000, monto_capital="0", monto_interes="50000")
    assert D(ab["interes_bien_comun"]) == 50000
    r = client.put(f"{API}/prestamos/{tercero['id']}/abonos/{ab['id']}", json={
        "prestamo_id": tercero["id"], "monto_abonado": "40000", "monto_capital": "0", "monto_interes": "40000",
    })
    assert r.status_code == 200, r.text
    assert D(r.json()["interes_bien_comun"]) == 40000


def test_prestamos_anteriores_a_la_regla_conservan_su_distribucion(client, socio, database_engine):
    primero = crear_prestamo(client, socio["id"])
    segundo = crear_prestamo(client, socio["id"])
    # Préstamos creados antes de esta actualización no tienen orden (NULL).
    with sessionmaker(bind=database_engine)() as db:
        db.execute(update(Prestamo).where(Prestamo.id.in_([primero["id"], segundo["id"]])).values(orden_socio=None))
        db.commit()
    detalle = client.get(f"{API}/prestamos/{segundo['id']}").json()
    assert detalle["es_segundo_prestamo"] is False
    assert {p["destino"] for p in detalle["periodos"]} == {"REPARTO_7_3"}
    ab = abonar(client, segundo["id"], 100000)
    assert D(ab["interes_bien_comun"]) == 30000
    # Un préstamo nuevo sí cuenta los anteriores en su orden histórico.
    assert crear_prestamo(client, socio["id"])["orden_socio"] == 3


def test_deducciones_consolidan_capital_intereses_y_multas(client, socio):
    sid = socio["id"]
    # Préstamo con dos meses vencidos sin pagar: 10 % de 1.000.000 por mes.
    prestamo = crear_prestamo(client, sid, meses_atras=3)
    client.post(f"{API}/socios/{sid}/movimientos", json={"tipo_movimiento": "MULTA", "monto": "20000", "descripcion": "Inasistencia"})
    multa_pagada = client.post(f"{API}/socios/{sid}/movimientos", json={"tipo_movimiento": "MULTA", "monto": "5000"}).json()
    client.post(f"{API}/socios/{sid}/movimientos", json={
        "tipo_movimiento": "PAGO_MULTA", "monto": "5000", "multa_id": multa_pagada["id"],
    })

    ded = perfil(client, sid)["deducciones"]
    assert D(ded["total_capital_pendiente"]) == 1000000
    assert D(ded["total_intereses_pendientes"]) == 200000
    assert D(ded["total_multas_pendientes"]) == 20000
    assert D(ded["total_deducciones"]) == 1220000
    assert [m["monto"] for m in ded["multas"]] == ["20000.00"]

    # Al abonar, las deducciones se actualizan solas.
    abonar(client, prestamo["id"], 100000, numero_cuota=1)
    ded = perfil(client, sid)["deducciones"]
    assert D(ded["total_intereses_pendientes"]) == 100000
    assert D(ded["total_deducciones"]) == 1120000


def test_total_ahorrado_suma_conceptos_sin_duplicar(client, socio):
    sid = socio["id"]
    otro = client.post(f"{API}/socios", json={
        "cedula": "987654321", "nombre": "Otro Socio", "telefono": "3009999999",
        "residencia": "Calle 2", "aporte_mensual": "100.00",
    }).json()
    client.post(f"{API}/socios/{sid}/movimientos", json={"tipo_movimiento": "APORTE", "monto": "300000"})
    client.post(f"{API}/socios/{otro['id']}/movimientos", json={"tipo_movimiento": "APORTE", "monto": "100000"})
    client.post(f"{API}/socios/{sid}/movimientos", json={"tipo_movimiento": "MULTA", "monto": "10000"})
    multa = perfil(client, sid)["multas"][0]
    client.post(f"{API}/socios/{sid}/movimientos", json={"tipo_movimiento": "PAGO_MULTA", "monto": "10000", "multa_id": multa["id"]})
    # Las ganancias en actividades son las líneas del apartado Actividades del socio.
    r = client.post(f"{API}/socios/{sid}/actividades", json={"nombre": "Costillas", "cantidad_vendida": 10, "ganancia": "20000"})
    assert r.status_code == 201, r.text
    client.post(f"{API}/socios/{sid}/actividades", json={"nombre": "Kits", "ganancia": "10000"})
    client.post(f"{API}/socios/{otro['id']}/actividades", json={"nombre": "Kits", "ganancia": "10000"})

    total = perfil(client, sid)["total_ahorrado_socio"]
    assert D(total["aportes_mensuales"]) == 300000
    assert D(total["ganancias_intereses"]) == 0
    assert D(total["ganancias_actividades"]) == 30000
    assert D(total["bien_comun"]) == 5000  # multa pagada repartida entre 2 socios
    componentes = ("aportes_mensuales", "ganancias_intereses", "ganancias_actividades",
                   "ganancias_rifas", "ganancias_reuniones", "bien_comun")
    assert D(total["total"]) == sum(D(total[c]) for c in componentes) == 335000
    otro_total = perfil(client, otro["id"])["total_ahorrado_socio"]
    assert D(otro_total["ganancias_actividades"]) == 10000
    assert D(otro_total["bien_comun"]) + D(total["bien_comun"]) == 10000


def test_abonos_aparecen_en_el_historial_del_socio_con_trazabilidad(client, socio):
    sid = socio["id"]
    prestamo = crear_prestamo(client, sid, monto="200000", cuotas=1)
    ab1 = abonar(client, prestamo["id"], 20000)
    movs = perfil(client, sid)["movimientos_prestamos"]
    assert [(m["tipo"], m["abono_id"], D(m["monto"])) for m in movs] == [("ABONO", ab1["id"], 20000)]
    assert movs[0]["prestamo_id"] == prestamo["id"] and movs[0]["numero_cuota"] == 1

    # Editar el abono: queda la corrección y el abono no se duplica.
    r = client.put(f"{API}/prestamos/{prestamo['id']}/abonos/{ab1['id']}", json={
        "prestamo_id": prestamo["id"], "monto_abonado": "25000",
    })
    assert r.status_code == 200, r.text
    movs = perfil(client, sid)["movimientos_prestamos"]
    assert sorted(m["tipo"] for m in movs) == ["ABONO", "EDICION"]
    assert sum(1 for m in movs if m["abono_id"] == ab1["id"] and m["tipo"] == "ABONO") == 1

    # Pago final: cancela el préstamo y se marca como PAGO.
    ab2 = abonar(client, prestamo["id"], 195000, monto_capital="195000", monto_interes="0")
    movs = perfil(client, sid)["movimientos_prestamos"]
    assert next(m for m in movs if m["abono_id"] == ab2["id"] and m["vigente"])["tipo"] == "PAGO"

    # Revertir el pago final: se conserva el registro original y aparece la reversión.
    historial = client.get(f"{API}/historial", params={"limit": 100}).json()
    lista = historial if isinstance(historial, list) else historial.get("items", [])
    creacion = next(h for h in lista if h["entidad_tipo"] == "AbonoPrestamo" and h["entidad_id"] == ab2["id"] and h["tipo_accion"] == "CREAR")
    assert client.post(f"{API}/historial/{creacion['id']}/revertir").status_code == 200
    movs = perfil(client, sid)["movimientos_prestamos"]
    del_ab2 = [m for m in movs if m["abono_id"] == ab2["id"]]
    assert sorted(m["tipo"] for m in del_ab2) == ["ABONO", "REVERSION"]
    assert next(m for m in del_ab2 if m["tipo"] == "ABONO")["vigente"] is False
    assert len({m["clave"] for m in movs}) == len(movs)


def test_hoja_imprimible_cuadra_con_total_ahorrado_y_deducciones(client, socio):
    sid = socio["id"]
    otro = client.post(f"{API}/socios", json={
        "cedula": "555666777", "nombre": "Zoila Tercera", "telefono": "3005555555",
        "residencia": "Calle 3", "aporte_mensual": "100.00",
    }).json()
    anio = hoy_colombia().year
    client.post(f"{API}/socios/{sid}/movimientos", json={
        "tipo_movimiento": "APORTE", "monto": "160000", "periodo": f"{anio}-01", "fecha": f"{anio}-01-15",
    })
    client.post(f"{API}/socios/{otro['id']}/movimientos", json={"tipo_movimiento": "APORTE", "monto": "100000"})
    # Rifa interna del apartado Eventos: ya no suma al socio (se registra en sus líneas).
    r = client.post(f"{API}/rifas", json={
        "nombre": "Interna Sep", "tipo": "INTERNA", "fecha": f"{anio}-01-20", "inversion_premios": "0",
        "valor_boleta": "60000", "total_boletas": "1", "boletas_vendidas": "1",
    })
    assert r.status_code == 201, r.text
    r = client.post(f"{API}/socios/{sid}/actividades", json={"tipo": "RIFA_INTERNA", "mes": 3, "ganancia": "39130"})
    assert r.status_code == 201 and r.json()["nombre"] == "Rifa interna" and r.json()["mes"] == 3
    client.post(f"{API}/socios/{sid}/actividades", json={"nombre": "Costillas", "cantidad_vendida": 5, "ganancia": "10200"})
    client.post(f"{API}/gastos-generales", json={"descripcion": "Papelería", "monto": "8001"})
    client.post(f"{API}/gastos-generales", json={"descripcion": "Declaración", "monto": "6000"})

    hoja = client.get(f"{API}/socios/{sid}/hoja-ahorro").json()
    total = perfil(client, sid)["total_ahorrado_socio"]
    assert hoja["socio"]["nombre"] == "Socio Prueba" and hoja["anio"] == anio
    assert D(hoja["meses"][0]["cuota"]) == 160000
    assert D(hoja["meses"][2]["rifa_interna"]) == 39130 and D(hoja["meses"][0]["rifa_interna"]) == 0
    assert D(total["ganancias_rifa_interna"]) == 39130 and D(total["ganancias_rifas"]) == 0
    assert "rifas_internas" not in hoja
    assert [(a["nombre"], a["cantidad_vendida"], D(a["ganancia"])) for a in hoja["actividades"]] == [("Costillas", 5, 10200)]
    assert D(total["ganancias_actividades"]) == 10200
    gastos = [f for f in hoja["deducciones"] if f["concepto"] in ("Papelería", "Declaración")]
    # Gastos repartidos en partes iguales entre 2 socios activos, sin perder centavos.
    assert sum(D(f["valor"]) for f in gastos) == D("7000.50")
    assert D(hoja["total_deducciones"]) == sum(D(f["valor"]) for f in hoja["deducciones"])
    assert client.get(f"{API}/socios/999999/hoja-ahorro").status_code == 404


def test_lineas_de_actividades_del_socio(client, socio):
    sid = socio["id"]
    base = f"{API}/socios/{sid}/actividades"
    r = client.post(base, json={"nombre": "  Rifa carro ", "ganancia": "2935920"})
    assert r.status_code == 201, r.text
    linea = r.json()
    assert linea["nombre"] == "Rifa carro" and linea["cantidad_vendida"] is None
    assert client.post(base, json={"nombre": "", "ganancia": "1"}).status_code == 422
    assert client.post(base, json={"nombre": "X", "ganancia": "-1"}).status_code == 422
    r = client.put(f"{base}/{linea['id']}", json={"nombre": "Rifa carro", "cantidad_vendida": 40, "ganancia": "3000000"})
    assert r.status_code == 200 and r.json()["cantidad_vendida"] == 40
    datos = perfil(client, sid)
    assert [a["id"] for a in datos["actividades"]] == [linea["id"]]
    assert D(datos["total_ahorrado_socio"]["ganancias_actividades"]) == 3000000
    assert client.delete(f"{base}/{linea['id']}").status_code == 200
    assert perfil(client, sid)["actividades"] == []
    assert client.delete(f"{base}/{linea['id']}").status_code == 404


def test_actividad_rifa_interna_requiere_mes_y_otra_requiere_nombre(client, socio):
    base = f"{API}/socios/{socio['id']}/actividades"
    assert client.post(base, json={"tipo": "RIFA_INTERNA", "ganancia": "1000"}).status_code == 422
    assert client.post(base, json={"tipo": "RIFA_INTERNA", "mes": 13, "ganancia": "1000"}).status_code == 422
    assert client.post(base, json={"tipo": "OTRA", "ganancia": "1000"}).status_code == 422
    otra = client.post(base, json={"tipo": "OTRA", "nombre": "Kits", "mes": 5, "ganancia": "1000"}).json()
    assert otra["tipo"] == "OTRA" and otra["mes"] is None
    # Cambiar una línea de "Otra" a "Rifa interna".
    r = client.put(f"{base}/{otra['id']}", json={"tipo": "RIFA_INTERNA", "mes": 9, "ganancia": "2000"})
    assert r.status_code == 200 and r.json()["tipo"] == "RIFA_INTERNA" and r.json()["mes"] == 9
