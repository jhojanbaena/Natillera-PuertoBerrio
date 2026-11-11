"""Modo demostración local SIN instalar base de datos.

Guarda todo en un archivo SQLite (backend/.demo/natillera_demo.sqlite) con
datos de ejemplo y el usuario admin / 12345678. Sirve solo para ver la app y
probar cambios en tu PC: nunca lo uses con datos reales ni en producción.

Uso (desde la carpeta backend, con el entorno virtual activo):
    python demo_local.py            # arranca la API en http://127.0.0.1:8000
    python demo_local.py --reset    # borra los datos de demo y vuelve a empezar

Luego, en otra terminal: cd frontend && npm run dev  ->  http://localhost:5173
"""
import os
import secrets
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
DEMO_DIR = BACKEND_DIR / ".demo"
DEMO_DB = DEMO_DIR / "natillera_demo.sqlite"
DEMO_DIR.mkdir(exist_ok=True)

if __name__ == "__main__" and "--reset" in sys.argv:
    DEMO_DB.unlink(missing_ok=True)
    print("Datos de demostración borrados. Ejecuta de nuevo: python demo_local.py")
    sys.exit(0)

# Clave aleatoria guardada solo en esta PC para que la sesión sobreviva a los reinicios.
_key_file = DEMO_DIR / "secret_key"
if not _key_file.exists():
    _key_file.write_text(secrets.token_hex(32), encoding="utf-8")

# La configuración exige una URL de PostgreSQL; esta nunca se conecta porque
# más abajo todas las sesiones se redirigen al archivo SQLite.
os.environ.update({
    "DATABASE_URL": "postgresql+psycopg2://demo:demo@127.0.0.1:1/no_se_usa",
    "SECRET_KEY": _key_file.read_text(encoding="utf-8").strip(),
    "ENVIRONMENT": "development",
    "AUTO_CREATE_TABLES": "False",
    "DEBUG": "False",
    "BACKEND_CORS_ORIGINS": "http://localhost:5173",
})

from sqlalchemy import create_engine, event, select  # noqa: E402

import app.core.database as database  # noqa: E402

sqlite_engine = create_engine(f"sqlite:///{DEMO_DB.as_posix()}", connect_args={"check_same_thread": False})


@event.listens_for(sqlite_engine, "connect")
def _foreign_keys(connection, _):
    connection.execute("PRAGMA foreign_keys=ON")


database.engine = sqlite_engine
database.SessionLocal.configure(bind=sqlite_engine)

from app.main import app  # noqa: E402,F401  (uvicorn importa "demo_local:app")
from app.models import Usuario  # noqa: E402


def _preparar_datos() -> None:
    database.Base.metadata.create_all(sqlite_engine)
    database.ensure_compatibility_columns()  # columnas nuevas en demos ya creadas
    with database.SessionLocal() as db:
        if db.execute(select(Usuario.id).limit(1)).first():
            return
    from seed import run_seed
    run_seed()


_preparar_datos()


if __name__ == "__main__":
    import uvicorn

    print("\nModo demo (SQLite, sin base de datos instalada)")
    print("  API:      http://127.0.0.1:8000/docs")
    print("  Frontend: cd frontend && npm run dev  ->  http://localhost:5173")
    print("  Usuario:  admin / 12345678\n")
    uvicorn.run("demo_local:app", host="127.0.0.1", port=8000, reload=True, reload_dirs=[str(BACKEND_DIR / "app")])
