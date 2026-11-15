"""Apartado Años: periodos independientes, copia de socios y años de solo consulta."""
from decimal import Decimal

from app.core.security import create_access_token

API = "/api/v1"


def _anio(client, anio=None):
    return {"X-Periodo": str(anio)} if anio else {}


def _socio(client, cedula, nombre, headers=None):
    r = client.post(f"{API}/socios", headers=headers or {}, json={
        "cedula": cedula, "nombre": nombre, "telefono": "3000000000",
        "residencia": "Puerto Berrío", "aporte_mensual": "50000.00",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _datos_del_anio(client, sid):
    assert client.post(f"{API}/socios/{sid}/movimientos", json={
        "tipo_movimiento": "APORTE", "monto": "50000.00", "descripcion": "Aporte",
    }).status_code == 201
    r = client.post(f"{API}/prestamos", json={
        "regla_interes": "FIJA", "socio_id": sid, "monto_prestado": "100000.00",
        "tasa_interes": "5.00", "numero_cuotas": 2,
    })
    assert r.status_code == 201, r.text
    assert client.post(f"{API}/gastos-generales", json={"descripcion": "Papelería", "monto": "10000.00"}).status_code == 201
    assert client.post(f"{API}/contabilidad/cuentas", json={"nombre": "Banco", "valor": "50000.00"}).status_code == 201


def test_estado_inicial_un_solo_anio_activo(client):
    actual = client.get(f"{API}/periodos/actual").json()
    assert actual["anio_activo"] == actual["anio_consultado"]
    assert actual["solo_lectura"] is False
    lista = client.get(f"{API}/periodos").json()
    assert [p["anio"] for p in lista["periodos"]] == [actual["anio_activo"]]
    assert lista["proximo_anio"] == actual["anio_activo"] + 1


def test_crear_anio_reinicia_todo_menos_socios(client):
    anio = client.get(f"{API}/periodos/actual").json()["anio_activo"]
    s1 = _socio(client, "100001", "Ana")
    s2 = _socio(client, "100002", "Beto")
    _datos_del_anio(client, s1["id"])

    r = client.post(f"{API}/periodos", json={"anio": anio + 1})
    assert r.status_code == 201, r.text
    assert r.json() == {"anio": anio + 1, "copiado_de_anio": anio, "socios_copiados": 2}

    # El año nuevo es el activo.
    actual = client.get(f"{API}/periodos/actual").json()
    assert actual == {"anio_activo": anio + 1, "anio_consultado": anio + 1, "solo_lectura": False}

    # Mismos socios, mismos ID y datos personales; sin movimientos.
    socios = {s["id"]: s for s in client.get(f"{API}/socios").json()}
    assert set(socios) == {s1["id"], s2["id"]}
    assert socios[s1["id"]]["cedula"] == "100001" and socios[s1["id"]]["nombre"] == "Ana"
    perfil = client.get(f"{API}/socios/{s1['id']}/perfil").json()
    assert Decimal(perfil["total_ahorrado"]) == 0
    assert client.get(f"{API}/prestamos").json() == []
    gastos = client.get(f"{API}/gastos-generales").json()
    assert gastos["anio"] == anio + 1 and gastos["gastos"] == []
    assert client.get(f"{API}/contabilidad").json()["cuentas"] == []
    assert client.get(f"{API}/finanzas/liquidacion-anual").json()["anio"] == anio + 1

    # El año anterior conserva todo intacto.
    viejo = _anio(client, anio)
    assert len(client.get(f"{API}/prestamos", headers=viejo).json()) == 1
    perfil_viejo = client.get(f"{API}/socios/{s1['id']}/perfil", headers=viejo).json()
    assert Decimal(perfil_viejo["total_ahorrado"]) == Decimal("50000")
    assert len(client.get(f"{API}/gastos-generales", headers=viejo).json()["gastos"]) == 1
    assert client.get(f"{API}/finanzas/liquidacion-anual", headers=viejo).json()["anio"] == anio

    resumen = {p["anio"]: p for p in client.get(f"{API}/periodos").json()["periodos"]}
    assert resumen[anio]["prestamos"] == 1 and Decimal(resumen[anio]["total_ahorro"]) == Decimal("50000")
    assert resumen[anio + 1]["prestamos"] == 0 and Decimal(resumen[anio + 1]["total_ahorro"]) == 0
    assert resumen[anio + 1]["socios"] == 2 and resumen[anio + 1]["activo"] is True


def test_no_se_crea_dos_veces_el_mismo_anio(client):
    anio = client.get(f"{API}/periodos/actual").json()["anio_activo"]
    _socio(client, "200001", "Carla")
    assert client.post(f"{API}/periodos", json={"anio": anio + 1}).status_code == 201
    repetido = client.post(f"{API}/periodos", json={"anio": anio + 1})
    assert repetido.status_code == 409
    # Un año que no es el siguiente tampoco se crea.
    assert client.post(f"{API}/periodos", json={"anio": anio + 5}).status_code == 409
    anios = [p["anio"] for p in client.get(f"{API}/periodos").json()["periodos"]]
    assert anios == [anio + 1, anio]
    # Los socios no se duplicaron.
    assert len(client.get(f"{API}/socios").json()) == 1


def test_socios_se_copian_del_ultimo_anio_y_cambios_no_son_retroactivos(client):
    anio = client.get(f"{API}/periodos/actual").json()["anio_activo"]
    s1 = _socio(client, "300001", "Diana")
    assert client.post(f"{API}/periodos", json={"anio": anio + 1}).status_code == 201

    # Cambios en el año nuevo: un socio editado y uno nuevo.
    assert client.put(f"{API}/socios/{s1['id']}", json={"nombre": "Diana Pérez"}).status_code == 200
    nuevo = _socio(client, "300002", "Esteban")

    viejo = client.get(f"{API}/socios", headers=_anio(client, anio)).json()
    assert [(s["id"], s["nombre"]) for s in viejo] == [(s1["id"], "Diana")]

    # El tercer año copia del segundo (incluido el socio nuevo y el nombre editado).
    r = client.post(f"{API}/periodos", json={"anio": anio + 2})
    assert r.status_code == 201 and r.json()["copiado_de_anio"] == anio + 1
    socios = {s["id"]: s["nombre"] for s in client.get(f"{API}/socios").json()}
    assert socios == {s1["id"]: "Diana Pérez", nuevo["id"]: "Esteban"}
    # Se pueden seguir creando socios (la secuencia de ID continúa).
    otro = _socio(client, "300003", "Fabio")
    assert otro["id"] not in socios


def test_anio_anterior_es_solo_consulta(client):
    anio = client.get(f"{API}/periodos/actual").json()["anio_activo"]
    s1 = _socio(client, "400001", "Gloria")
    assert client.post(f"{API}/periodos", json={"anio": anio + 1}).status_code == 201
    viejo = _anio(client, anio)

    assert client.get(f"{API}/periodos/actual", headers=viejo).json()["solo_lectura"] is True
    intentos = [
        client.post(f"{API}/socios", headers=viejo, json={
            "cedula": "400002", "nombre": "Nuevo X", "telefono": "3000000001", "residencia": "Calle 1", "aporte_mensual": "1.00"}),
        client.put(f"{API}/socios/{s1['id']}", headers=viejo, json={"nombre": "Cambiado"}),
        client.post(f"{API}/socios/{s1['id']}/movimientos", headers=viejo, json={
            "tipo_movimiento": "APORTE", "monto": "10.00", "descripcion": "x"}),
        client.post(f"{API}/gastos-generales", headers=viejo, json={"descripcion": "x", "monto": "1.00"}),
        client.delete(f"{API}/socios/{s1['id']}", headers=viejo),
    ]
    assert [r.status_code for r in intentos] == [403] * len(intentos), [r.text for r in intentos]
    assert "solo consulta" in intentos[0].json()["detail"]
    assert client.get(f"{API}/socios", headers=viejo).json()[0]["nombre"] == "Gloria"

    # Un año inexistente no se puede consultar.
    assert client.get(f"{API}/socios", headers=_anio(client, 1999)).status_code == 404


def test_solo_admin_crea_anios(client):
    anio = client.get(f"{API}/periodos/actual").json()["anio_activo"]
    client.headers["Authorization"] = "Bearer " + create_access_token("reader-test")
    assert client.post(f"{API}/periodos", json={"anio": anio + 1}).status_code == 403
    assert len(client.get(f"{API}/periodos").json()["periodos"]) == 1
