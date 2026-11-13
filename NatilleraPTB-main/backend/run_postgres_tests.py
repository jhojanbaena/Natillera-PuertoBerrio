"""Ejecuta pytest en natillera_test local, usando esquemas desechables por caso."""
import os
from pathlib import Path
import subprocess
import sys

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main() -> int:
    backend = Path(__file__).resolve().parent
    # Solo archivo local, sin heredar una DATABASE_URL de otro entorno.
    config = dotenv_values(backend / ".env")
    if not config.get("DATABASE_URL"):
        raise SystemExit("Falta backend/.env: ejecuta python backend/setup_local.py")
    url = make_url(config["DATABASE_URL"])
    if url.get_backend_name() != "postgresql" or url.host not in {"localhost", "127.0.0.1"}:
        raise SystemExit("Las pruebas solo admiten PostgreSQL local")
    engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            exists = connection.execute(text(
                "SELECT 1 FROM pg_database WHERE datname = :name"
            ), {"name": "natillera_test"}).scalar()
            if not exists:
                connection.execute(text("CREATE DATABASE natillera_test"))
    finally:
        engine.dispose()
    env = dict(os.environ)
    env["TEST_DATABASE_URL"] = url.set(database="natillera_test").render_as_string(hide_password=False)
    print("Ejecutando pruebas en natillera_test, con esquemas aislados por caso.", flush=True)
    return subprocess.run(
        [sys.executable, "-m", "pytest", *sys.argv[1:]], cwd=backend, env=env,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
