"""Rol Desarrollador (solo Panel) y apartado Estadísticas (datos reales y fotografías guardadas)."""
import pytest

from app.core.security import create_access_token
from app.services.prestamos_service import hoy_colombia

API = "/api/v1"


def _como(client, usuario):
    client.headers["Authorization"] = "Bearer " + create_access_token(usuario)


# ---------------------------------------------------------------------------
# Rol Desarrollador
# ---------------------------------------------------------------------------

def test_perfil_indica_rol(client):
    assert client.get(API + "/auth/me").json()["is_developer"] is False
    _como(client, "dev-test")
    perfil = client.get(API + "/auth/me")
    assert perfil.status_code == 200
    assert perfil.json()["is_developer"] is True
    assert perfil.json()["is_admin"] is False


@pytest.mark.parametrize("usuario", ["admin-test", "reader-test"])
def test_panel_rechaza_admin_y_usuarios(client, usuario):
    _como(client, usuario)
    assert client.get(API + "/panel").status_code == 403


def test_panel_accesible_para_desarrollador(client):
    _como(client, "dev-test")
    assert client.get(API + "/panel").status_code == 200


@pytest.mark.parametrize("path", [
    "/dashboard", "/socios", "/prestamos", "/actividades", "/rifas", "/historial", "/gastos-generales",
    "/contabilidad", "/periodos", "/periodos/actual", "/finanzas", "/estadisticas", "/estadisticas/guardadas",
])
def test_desarrollador_ve_todos_los_modulos(client, path):
    _como(client, "dev-test")
    assert client.get(API + path).status_code == 200


def test_desarrollador_tiene_permisos_de_administrador(client):
    _como(client, "dev-test")
    socio = {"cedula": "987654321", "nombre": "Socio Dev", "telefono": "3001234567", "residencia": "Calle de prueba 123", "aporte_mensual": "130000.00"}
    assert client.post(API + "/socios", json=socio).status_code == 201
    assert client.post(API + "/estadisticas/guardadas", json={"nombre": "Dev", "filtros": {}}).status_code == 201


def test_registro_no_crea_desarrolladores(client):
    body = {"username": "nuevo-user", "password": "password-segura", "is_developer": True}
    assert client.post(API + "/auth/register", json=body).status_code == 422


# ---------------------------------------------------------------------------
# Estadísticas
# ---------------------------------------------------------------------------

def _movimiento(client, sid, tipo, monto):
    r = client.post(f"{API}/socios/{sid}/movimientos", json={"tipo_movimiento": tipo, "monto": monto})
    assert r.status_code == 201, r.text


def test_estadistica_vacia_sin_datos_ficticios(client):
    r = client.get(API + "/estadisticas")
    assert r.status_code == 200
    data = r.json()
    assert data["totales"] == {"ingresos": 0, "egresos": 0, "otros": 0, "balance": 0, "cantidad": 0}
    assert data["serie"] == [] and data["por_tipo"] == []


def test_estadistica_con_movimientos_reales_y_filtros(client, socio):
    hoy = hoy_colombia().isoformat()
    _movimiento(client, socio["id"], "APORTE", "1000")
    _movimiento(client, socio["id"], "MULTA", "200")
    assert client.post(API + "/actividades", json={
        "nombre": "Bingo", "grupo_encargado": "Grupo", "fecha": hoy, "inversion": "300", "ingresos_brutos": "900",
    }).status_code == 201

    data = client.get(API + "/estadisticas", params={"fecha_desde": hoy, "fecha_hasta": hoy}).json()
    assert data["totales"]["ingresos"] == 1900
    assert data["totales"]["egresos"] == 300
    assert data["totales"]["otros"] == 200
    assert data["totales"]["balance"] == 1600
    assert data["granularidad"] == "dia" and len(data["serie"]) == 1

    solo_ingresos = client.get(API + "/estadisticas", params={"tipos": "APORTE"}).json()
    assert solo_ingresos["totales"]["ingresos"] == 1000 and solo_ingresos["totales"]["cantidad"] == 1

    opciones = client.get(API + "/estadisticas/opciones").json()
    clave = next(e["clave"] for e in opciones["eventos"] if e["nombre"] == "Bingo")
    evento = client.get(API + "/estadisticas", params={"evento": clave}).json()
    assert evento["totales"]["ingresos"] == 900 and evento["totales"]["egresos"] == 300
    assert evento["por_evento"][0]["balance"] == 600

    # Fuera del rango no hay movimientos.
    vacio = client.get(API + "/estadisticas", params={"fecha_desde": "2000-01-01", "fecha_hasta": "2000-01-31"}).json()
    assert vacio["totales"]["cantidad"] == 0


@pytest.mark.parametrize("params", [
    {"tipos": "INVENTADO"}, {"evento": "socio-1"}, {"fecha_desde": "2026-05-01", "fecha_hasta": "2026-04-01"},
])
def test_filtros_invalidos(client, params):
    assert client.get(API + "/estadisticas", params=params).status_code == 422


def test_estadistica_guardada_no_cambia(client, socio):
    _movimiento(client, socio["id"], "APORTE", "1000")
    r = client.post(API + "/estadisticas/guardadas", json={"nombre": "  Corte  ", "filtros": {"modo": "todo"}})
    assert r.status_code == 201, r.text
    guardada = r.json()
    assert guardada["nombre"] == "Corte" and guardada["totales"]["ingresos"] == 1000

    _movimiento(client, socio["id"], "APORTE", "5000")
    assert client.get(API + "/estadisticas").json()["totales"]["ingresos"] == 6000
    otra_vez = client.get(f"{API}/estadisticas/guardadas/{guardada['id']}").json()
    assert otra_vez["resultados"]["totales"]["ingresos"] == 1000
    lista = client.get(API + "/estadisticas/guardadas").json()
    assert [e["id"] for e in lista] == [guardada["id"]]


def test_guardar_y_eliminar_solo_admin(client):
    r = client.post(API + "/estadisticas/guardadas", json={"nombre": "A", "filtros": {}})
    assert r.status_code == 201
    _como(client, "reader-test")
    assert client.get(API + "/estadisticas/guardadas").status_code == 200
    assert client.post(API + "/estadisticas/guardadas", json={"nombre": "B", "filtros": {}}).status_code == 403
    assert client.delete(f"{API}/estadisticas/guardadas/{r.json()['id']}").status_code == 403
    _como(client, "admin-test")
    assert client.delete(f"{API}/estadisticas/guardadas/{r.json()['id']}").status_code == 204
    assert client.get(API + "/estadisticas/guardadas").json() == []
