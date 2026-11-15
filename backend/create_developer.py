"""Crea la cuenta con el rol Desarrollador (contraseña interactiva).

Este rol es independiente del Administrador: solo da acceso al apartado Panel.
Solo puede existir una cuenta de Desarrollador y no se puede asignar desde la
aplicación, únicamente con este script.

    python create_developer.py
"""
from getpass import getpass
from sqlalchemy import select
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models import Usuario
from app.schemas.usuario import UsuarioCreate


def main():
    username = input("Usuario desarrollador: ").strip()
    nombre = input("Nombre completo (opcional): ").strip() or None
    password = getpass("Contraseña (12 caracteres mínimo, 72 bytes máximo): ")
    if password != getpass("Repetir contraseña: "):
        raise SystemExit("Las contraseñas no coinciden")
    data = UsuarioCreate(username=username, nombre_completo=nombre, password=password)
    with SessionLocal.begin() as db:
        if db.execute(select(Usuario.id).where(Usuario.is_developer.is_(True))).first():
            raise SystemExit("Ya existe una cuenta de Desarrollador")
        if db.execute(select(Usuario.id).where(Usuario.username == data.username)).first():
            raise SystemExit("El nombre de usuario ya está registrado")
        db.add(Usuario(
            username=data.username,
            nombre_completo=data.nombre_completo,
            password_hash=get_password_hash(data.password),
            is_admin=False,
            is_developer=True,
            is_active=True,
        ))
    print("Desarrollador creado")


if __name__ == "__main__":
    main()
