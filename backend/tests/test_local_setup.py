"""Regresión para configuración local y ubicación estable de .env."""
import os
from pathlib import Path
import subprocess
import sys

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

from app.core.config import ENV_FILE, Settings
from setup_local import BACKEND_DIR, create_local_env


def test_setup_generates_matching_database_credentials(tmp_path):
    destination = tmp_path / ".env"
    assert create_local_env(destination)
    config = dotenv_values(destination)
    url = make_url(config["DATABASE_URL"])
    assert url.drivername == "postgresql+psycopg2"
    assert url.username == config["POSTGRES_USER"]
    assert url.password == config["POSTGRES_PASSWORD"]
    assert url.database == config["POSTGRES_DB"]
    assert url.port == int(config["POSTGRES_PORT"])
    assert len(config["SECRET_KEY"]) >= 32
    assert "REEMPLAZAR_" not in destination.read_text()
    if os.name == "posix":
        assert destination.stat().st_mode & 0o777 == 0o600


def test_setup_preserves_existing_env(tmp_path):
    destination = tmp_path / ".env"
    destination.write_text("existing configuration\n")
    assert not create_local_env(destination)
    assert destination.read_text() == "existing configuration\n"


def test_env_location_does_not_depend_on_working_directory(tmp_path):
    assert ENV_FILE == BACKEND_DIR / ".env"
    # Un .env ajeno en cwd no debe ser leído. Se usan valores sintéticos del fixture.
    (tmp_path / ".env").write_text("SECRET_KEY=short\nDATABASE_URL=sqlite://\n")
    environment = dict(os.environ, PYTHONPATH=str(BACKEND_DIR))
    result = subprocess.run(
        [sys.executable, "-c", "from app.core.config import ENV_FILE; print(ENV_FILE)"],
        cwd=tmp_path, env=environment, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == ENV_FILE


def test_short_secret_has_actionable_error():
    import pytest
    with pytest.raises(ValueError, match="SECRET_KEY debe tener al menos 32 caracteres"):
        Settings(SECRET_KEY="short", _env_file=None)
