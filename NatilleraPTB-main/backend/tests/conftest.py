"""SQLite desechable o PostgreSQL local natillera_test con esquemas aislados.

No se ejecuta el lifespan productivo ni sus cambios de compatibilidad de esquema.
"""
import os
from uuid import uuid4

# Configuración sintética antes de importar la aplicación; nunca leer credenciales.
os.environ["DATABASE_URL"] = "postgresql+psycopg2://test:test@127.0.0.1:1/natillera_test"
os.environ["SECRET_KEY"] = "test-only-secret-key-with-at-least-32-characters"
os.environ["DEBUG"] = "False"
os.environ["ENVIRONMENT"] = "test"
os.environ["BACKEND_CORS_ORIGINS"] = "http://localhost:5173"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.database import Base, get_db
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.usuario import Usuario


@pytest.fixture(scope="session")
def password_hash():
    return get_password_hash("test-password")


@pytest.fixture
def database_engine():
    postgres_url = os.environ.get("TEST_DATABASE_URL")
    schema = None
    if postgres_url:
        url = make_url(postgres_url)
        if url.get_backend_name() != "postgresql" or url.database != "natillera_test" or url.host not in {"127.0.0.1", "localhost"}:
            raise ValueError("TEST_DATABASE_URL debe apuntar a PostgreSQL local y a la base natillera_test")
        schema = "test_" + uuid4().hex
        engine = create_engine(url, execution_options={"schema_translate_map": {None: schema}})
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    try:
        yield engine
    finally:
        if schema:
            with engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


@pytest.fixture
def client(password_hash, database_engine):
    engine = database_engine
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    with sessions() as db:
        db.add_all([
            Usuario(username="admin-test", password_hash=password_hash, is_admin=True),
            Usuario(username="reader-test", password_hash=password_hash, is_admin=False),
            Usuario(username="inactive-test", password_hash=password_hash, is_active=False),
        ])
        db.commit()

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        # Sin context manager: TestClient no ejecuta el lifespan de producción.
        with_client = TestClient(app)
        with_client.headers["Authorization"] = "Bearer " + create_access_token("admin-test")
        yield with_client
    finally:
        with_client.close()
        app.dependency_overrides.clear()


@pytest.fixture
def socio(client):
    response = client.post("/api/v1/socios", json={
        "cedula": "123456789", "nombre": "Socio Prueba", "telefono": "3001234567",
        "residencia": "Calle de prueba 123", "aporte_mensual": "100.00",
    })
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def prestamo(client, socio):
    response = client.post("/api/v1/prestamos", json={
        "socio_id": socio["id"], "monto_prestado": "1000.00",
        "tasa_interes": "10.00", "numero_cuotas": 2,
        "fecha_prestamo": "2026-01-01", "fecha_vencimiento": "2026-03-01",
    })
    assert response.status_code == 201, response.text
    return response.json()
