"""Crea el primer administrador con contraseña interactiva, sin datos de ejemplo."""
from getpass import getpass
from sqlalchemy import select
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models import Usuario
from app.schemas.usuario import UsuarioCreate


def main():
    username = input("Usuario administrador: ").strip()
    password = getpass("Contraseña (12 caracteres mínimo, 72 bytes máximo): ")
    if password != getpass("Repetir contraseña: "):
        raise SystemExit("Las contraseñas no coinciden")
    data = UsuarioCreate(username=username, password=password)
    with SessionLocal.begin() as db:
        if db.execute(select(Usuario.id).where(Usuario.is_admin.is_(True))).first():
            raise SystemExit("Ya existe un administrador; use la gestión de usuarios")
        db.add(Usuario(username=data.username, password_hash=get_password_hash(data.password), is_admin=True, is_active=True))
    print("Administrador creado")


if __name__ == "__main__":
    main()
