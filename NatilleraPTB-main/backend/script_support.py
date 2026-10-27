"""Errores legibles para los comandos de instalación, sin exponer credenciales."""
import sys


def require_schema(connection, metadata):
    from sqlalchemy import inspect

    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    for table in metadata.sorted_tables:
        if table.name not in tables or not set(table.columns.keys()) <= {
            column["name"] for column in inspector.get_columns(table.name)
        }:
            raise SystemExit(
                "La base de datos no está inicializada o tiene un esquema antiguo. "
                "Desde backend ejecuta: python manage_db.py upgrade"
            )


def run_command(command):
    try:
        # Dentro del try para detectar también dependencias ausentes al importar.
        from pydantic import ValidationError
        from sqlalchemy.exc import IntegrityError, SQLAlchemyError

        try:
            command()
        except ValidationError as exc:
            # Nunca imprimir ValidationError completo: incluye valores de entrada.
            errors = "; ".join(
                f"{'.'.join(map(str, error['loc'])) or 'configuración'}: {error['msg']}"
                for error in exc.errors(include_input=False, include_context=False)
                if error['type'] != 'value_error'
            )
            print(
                "Datos o configuración inválidos. " + (errors + ". " if errors else "")
                + "Revisa backend/.env (DATABASE_URL y SECRET_KEY). Para un entorno local nuevo "
                "ejecuta python backend/setup_local.py desde la raíz. El usuario requiere "
                "3 a 50 caracteres y la contraseña 12 caracteres mínimo y 72 bytes UTF-8 máximo.",
                file=sys.stderr,
            )
            return 1
        except IntegrityError:
            print("Los datos entran en conflicto con registros existentes o restricciones de la base. No se guardaron los cambios de esta ejecución.", file=sys.stderr)
            return 1
        except SQLAlchemyError:
            print("No se pudo completar la operación en PostgreSQL. Revisa DATABASE_URL, que el servidor esté iniciado y ejecuta python manage_db.py upgrade desde backend. No se guardaron los cambios de esta ejecución.", file=sys.stderr)
            return 1
    except ModuleNotFoundError as exc:
        print(f"Falta la dependencia {exc.name}. Activa el entorno virtual e instala: python -m pip install -r backend/requirements.txt (desde la raíz).", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("Operación cancelada; ejecuta el comando en una terminal interactiva.", file=sys.stderr)
        return 1
    return 0
