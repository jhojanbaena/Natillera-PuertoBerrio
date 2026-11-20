"""Permitir vista a los socios: configuración del Panel (DEV) y portal del socio."""
import re

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, create_socio_token
from app.core.vista_socios import huella_cedula
from app.main import app
from app.models.historial import HistorialMovimiento

API = "/api/v1"
PANEL = API + "/panel/vista-socios"
LOGIN = API + "/portal-socio/login"
HOJA = API + "/portal-socio/mi-hoja"


def _como(client, usuario):
    client.headers["Authorization"] = "Bearer " + create_access_token(usuario)


def _crear_socio(client, cedula, nombre, socio_id=None):
    body = {"cedula": cedula, "nombre": nombre, "telefono": "3001234567",
            "residencia": "Calle de prueba 123", "aporte_mensual": "130000.00"}
    if socio_id is not None:
        body["id"] = socio_id
    r = client.post(API + "/socios", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _configurar(client, modo, inicio=None, fin=None):
    previo = client.headers.get("Authorization")
    _como(client, "dev-test")
    r = client.put(PANEL, json={"modo": modo, "id_inicio": inicio, "id_fin": fin})
    client.headers["Authorization"] = previo
    assert r.status_code == 200, r.text
    return r.json()


def _login(client, usuario, password=None):
    return client.post(LOGIN, json={"username": usuario, "password": usuario if password is None else password},
                       headers={"Authorization": ""})


def _hoja(client, token, **headers):
    return client.get(HOJA, headers={"Authorization": "Bearer " + token, **headers})


@pytest.fixture
def socios(client):
    return {
        "ana": _crear_socio(client, "1020304050", "Ana Pérez", 5),
        "luis": _crear_socio(client, "98765432", "Luis Gómez", 10),
        "extranjero": _crear_socio(client, "CE 20318620", "John Smith", 20),
        "provisional": _crear_socio(client, "11111111", "Socio Provisional", 7),
    }


# ---------------------------------------------------------------------------
# Panel: solo el rol Desarrollador
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("usuario", ["admin-test", "reader-test"])
def test_panel_vista_socios_solo_desarrollador(client, usuario):
    _como(client, usuario)
    assert client.get(PANEL).status_code == 403
    assert client.put(PANEL, json={"modo": "TODOS"}).status_code == 403


def test_configuracion_por_defecto_desactivada(client, socios):
    _como(client, "dev-test")
    datos = client.get(PANEL).json()
    assert datos["modo"] == "DESACTIVADO"
    assert datos["socios_con_acceso"] == 0
    assert _login(client, "1020304050").status_code == 403


def test_validacion_del_rango(client):
    _como(client, "dev-test")
    assert client.put(PANEL, json={"modo": "RANGO", "id_inicio": 10}).status_code == 422
    assert client.put(PANEL, json={"modo": "RANGO", "id_inicio": 10, "id_fin": 5}).status_code == 422
    assert client.put(PANEL, json={"modo": "RANGO", "id_inicio": 0, "id_fin": 5}).status_code == 422
    assert client.put(PANEL, json={"modo": "OTRO"}).status_code == 422
    r = client.put(PANEL, json={"modo": "TODOS", "id_inicio": 1, "id_fin": 3})
    assert r.status_code == 200 and r.json()["id_inicio"] is None


def test_conteos_del_panel(client, socios):
    datos = _configurar(client, "TODOS")
    assert datos["modo"] == "TODOS"
    assert datos["socios_con_acceso"] == 3
    assert datos["socios_bloqueados"] == 1  # cédula provisional
    datos = _configurar(client, "RANGO", 5, 10)
    assert (datos["id_inicio"], datos["id_fin"]) == (5, 10)
    assert datos["socios_con_acceso"] == 2 and datos["socios_bloqueados"] == 1
    assert datos["actualizado_por"] == "dev-test"


# ---------------------------------------------------------------------------
# Login del socio
# ---------------------------------------------------------------------------

def test_modalidad_todos_incluye_socios_nuevos(client, socios):
    _configurar(client, "TODOS")
    assert _login(client, "1020304050").status_code == 200
    nuevo = _crear_socio(client, "55667788", "Socio Nuevo")
    r = _login(client, "55667788")
    assert r.status_code == 200
    assert _hoja(client, r.json()["access_token"]).json()["socio"]["id"] == nuevo["id"]


def test_modalidad_rango(client, socios):
    _configurar(client, "RANGO", 5, 10)
    assert _login(client, "1020304050").status_code == 200   # ID 5
    assert _login(client, "98765432").status_code == 200     # ID 10
    assert _login(client, "20318620").status_code == 401     # ID 20, fuera del rango
    _crear_socio(client, "44556677", "Fuera De Rango", 30)
    assert _login(client, "44556677").status_code == 401
    _crear_socio(client, "33445566", "Dentro De Rango", 8)
    assert _login(client, "33445566").status_code == 200


def test_credenciales_invalidas(client, socios):
    _configurar(client, "TODOS")
    assert _login(client, "1020304050", "98765432").status_code == 401   # contraseña de otro
    assert _login(client, "1020304050", "1020304051").status_code == 401
    assert _login(client, "00000000").status_code == 401                 # no existe
    assert _login(client, "Ana Pérez").status_code == 401                # solo cédula, no nombre
    assert _login(client, "CE 20318620").status_code == 401              # solo números
    assert _login(client, "20318620").status_code == 200                 # cédula extranjera con sus cifras


def test_cedulas_provisionales_bloqueadas(client, socios):
    _configurar(client, "TODOS")
    assert _login(client, "11111111").status_code == 401
    for cedula in ("2222222222", "3333333333"):
        _crear_socio(client, cedula, "Provisional " + cedula[0])
        assert _login(client, cedula).status_code == 401


def test_socio_inactivo_no_entra(client, socios):
    _configurar(client, "TODOS")
    token = _login(client, "98765432").json()["access_token"]
    assert client.delete(API + f"/socios/{socios['luis']['id']}").status_code == 200
    assert _login(client, "98765432").status_code == 401
    assert _hoja(client, token).status_code == 401


def test_limite_de_intentos(client, socios):
    _configurar(client, "TODOS")
    for _ in range(10):
        assert _login(client, "1020304050", "1").status_code == 401
    assert _login(client, "1020304050").status_code == 429


# ---------------------------------------------------------------------------
# Ficha del socio
# ---------------------------------------------------------------------------

def test_hoja_igual_a_la_del_administrador(client, socios):
    socio_id = socios["ana"]["id"]
    assert client.post(API + f"/socios/{socio_id}/movimientos", json={
        "tipo_movimiento": "APORTE", "monto": "130000.00", "fecha": "2026-02-10", "periodo": "2026-02",
    }).status_code == 201
    _configurar(client, "TODOS")
    token = _login(client, "1020304050").json()["access_token"]
    propia = _hoja(client, token)
    assert propia.status_code == 200
    assert propia.json() == client.get(API + f"/socios/{socio_id}/hoja-ahorro").json()


def test_id_sale_del_token_no_de_la_url(client, socios):
    _configurar(client, "TODOS")
    token = _login(client, "1020304050").json()["access_token"]
    r = client.get(HOJA + f"?socio_id={socios['luis']['id']}", headers={"Authorization": "Bearer " + token})
    assert r.json()["socio"]["id"] == socios["ana"]["id"]
    # El token de socio no abre la hoja de nadie por la ruta del administrador.
    otra = client.get(API + f"/socios/{socios['luis']['id']}/hoja-ahorro", headers={"Authorization": "Bearer " + token})
    assert otra.status_code == 401


def test_desactivar_cierra_sesiones_aunque_se_reactive(client, socios):
    _configurar(client, "TODOS")
    token = _login(client, "1020304050").json()["access_token"]
    assert _hoja(client, token).status_code == 200
    _configurar(client, "DESACTIVADO")
    assert _hoja(client, token).status_code == 401
    _configurar(client, "TODOS")
    assert _hoja(client, token).status_code == 401  # la sesión vieja no revive
    assert _hoja(client, _login(client, "1020304050").json()["access_token"]).status_code == 200


def test_cambio_de_rango_corta_acceso(client, socios):
    _configurar(client, "TODOS")
    token = _login(client, "20318620").json()["access_token"]
    assert _hoja(client, token).status_code == 200
    _configurar(client, "RANGO", 1, 10)
    assert _hoja(client, token).status_code == 401
    _configurar(client, "RANGO", 1, 20)
    assert _hoja(client, token).status_code == 200


def test_token_no_sirve_si_el_id_cambia_de_duenio(client, socios):
    _configurar(client, "TODOS")
    token = _login(client, "1020304050").json()["access_token"]  # ID 5
    assert client.put(API + f"/socios/{socios['ana']['id']}", json={"id": 50}).status_code == 200
    _crear_socio(client, "12121299", "Otra Persona", 5)
    assert _hoja(client, token).status_code == 401


def test_token_falsificado_o_de_admin(client, socios):
    _configurar(client, "TODOS")
    # Token de socio para otro ID sin la huella correcta.
    falso = create_socio_token(socios["luis"]["id"], huella_cedula("1020304050"), 1)
    assert _hoja(client, falso).status_code == 401
    # Token de administrador o Desarrollador no abre el portal.
    assert _hoja(client, create_access_token("admin-test")).status_code == 401
    assert _hoja(client, create_access_token("dev-test")).status_code == 401


def test_portal_solo_muestra_el_anio_activo(client, socios):
    from app.services.prestamos_service import hoy_colombia
    anio = hoy_colombia().year
    socio_id = socios["ana"]["id"]
    assert client.post(API + f"/socios/{socio_id}/movimientos", json={
        "tipo_movimiento": "APORTE", "monto": "130000.00", "fecha": f"{anio}-02-10", "periodo": f"{anio}-02",
    }).status_code == 201
    assert client.post(API + "/periodos", json={"anio": anio + 1}).status_code == 201
    _configurar(client, "TODOS")
    token = _login(client, "1020304050").json()["access_token"]
    # Aunque pida el año anterior, ve el año activo (nuevo, sin aportes).
    r = _hoja(client, token, **{"X-Periodo": str(anio)})
    assert r.status_code == 200
    assert r.json()["anio"] == anio + 1
    assert r.json() == client.get(API + f"/socios/{socio_id}/hoja-ahorro").json()


def test_token_de_socio_rechazado_en_todo_lo_demas(client, socios):
    _configurar(client, "TODOS")
    token = _login(client, "1020304050").json()["access_token"]
    libres = {"/", "/auth/login", "/auth/login-json", "/portal-socio/login", "/portal-socio/mi-hoja"}
    revisadas = 0
    for ruta, operaciones in app.openapi()["paths"].items():
        if not ruta.startswith(API) or ruta[len(API):] in libres:
            continue
        url = re.sub(r"\{[^}]+\}", "1", ruta)
        for metodo in operaciones:
            r = client.request(metodo.upper(), url, headers={"Authorization": "Bearer " + token}, json={})
            assert r.status_code == 401, (metodo, ruta, r.status_code)
            revisadas += 1
    assert revisadas > 50


def test_no_registra_cedulas_en_historial(client, socios, database_engine):
    from sqlalchemy.orm import Session
    with Session(database_engine) as db:
        antes = db.execute(select(HistorialMovimiento.id)).all()
    _configurar(client, "TODOS")
    token = _login(client, "1020304050").json()["access_token"]
    _hoja(client, token)
    _configurar(client, "DESACTIVADO")
    with Session(database_engine) as db:
        despues = db.execute(select(HistorialMovimiento.id)).all()
    assert len(antes) == len(despues)
