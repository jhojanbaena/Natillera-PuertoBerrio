"""Genera configuración de desarrollo local, sin sobrescribir archivos existentes."""
from pathlib import Path
import secrets

BACKEND_DIR = Path(__file__).resolve().parent


def create_local_env(destination: Path = BACKEND_DIR / ".env") -> bool:
    template = (BACKEND_DIR / ".env.example").read_text(encoding="utf-8")
    content = template.replace("REEMPLAZAR_SECRET_KEY", secrets.token_hex(32))
    content = content.replace("REEMPLAZAR_POSTGRES_PASSWORD", secrets.token_hex(24))
    try:
        # Creación exclusiva: conservar credenciales y configuración ya existentes.
        with destination.open("x", encoding="utf-8") as file:
            destination.chmod(0o600)
            file.write(content)
    except FileExistsError:
        return False
    return True


if __name__ == "__main__":
    if create_local_env():
        print("Creado backend/.env con credenciales locales aleatorias (no se muestran).")
    else:
        print("backend/.env ya existe; se conserva sin cambios.")
    print("Desde la raíz: docker compose --env-file backend/.env up -d --wait db")
