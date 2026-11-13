"""Auditoría de solo lectura y migración PostgreSQL transaccional.

python manage_db.py check
python manage_db.py upgrade       # DDL explícito, requiere respaldo previo
"""
import argparse
import json
from sqlalchemy import inspect, text
from sqlalchemy.schema import AddConstraint
from app.core.database import Base, engine
from app.core.integrity import CHECKS
import app.models  # noqa: F401


def audit(connection):
    issues = {}
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    missing = set(Base.metadata.tables) - tables
    for name in sorted(missing):
        issues[f"tabla_ausente:{name}"] = 1
    for table_name, checks in CHECKS.items():
        if table_name not in tables:
            continue
        for name, expression in checks.items():
            count = connection.execute(text(f'SELECT count(*) FROM "{table_name}" WHERE NOT ({expression})')).scalar_one()
            if count:
                issues[name] = count
    for table in Base.metadata.sorted_tables:
        if table.name not in tables:
            continue
        for fk in table.foreign_keys:
            if fk.column.table.name not in tables:
                continue
            count = connection.execute(text(
                f'SELECT count(*) FROM "{table.name}" c LEFT JOIN "{fk.column.table.name}" p '
                f'ON c."{fk.parent.name}" = p."{fk.column.name}" '
                f'WHERE c."{fk.parent.name}" IS NOT NULL AND p."{fk.column.name}" IS NULL'
            )).scalar_one()
            if count:
                issues[f"huerfanos:{table.name}.{fk.parent.name}"] = count
    if {"prestamos", "abonos_prestamo"} <= tables:
        count = connection.execute(text('''
            SELECT count(*) FROM prestamos p LEFT JOIN (
                SELECT prestamo_id, sum(monto_capital) capital, sum(monto_interes) interes, count(*) cuotas
                FROM abonos_prestamo GROUP BY prestamo_id
            ) a ON a.prestamo_id = p.id
            WHERE coalesce(a.capital, 0) > p.monto_prestado
               OR p.saldo_pendiente <> p.monto_prestado - coalesce(a.capital, 0)
               OR p.cuotas_pagadas <> coalesce(a.cuotas, 0)
               OR (p.estado = 'PAGADO' AND (p.saldo_pendiente <> 0 OR coalesce(a.interes, 0) < p.total_intereses))
        ''')).scalar_one()
        if count:
            issues["prestamos_descuadrados"] = count
    if "finanzas_socio" in tables:
        count = connection.execute(text('''
            SELECT count(*) FROM (
                SELECT socio_id FROM finanzas_socio GROUP BY socio_id
                HAVING sum(CASE WHEN tipo_movimiento = 'APORTE' THEN monto WHEN tipo_movimiento = 'RETIRO_AHORRO' THEN -monto ELSE 0 END) < 0
            ) s
        ''')).scalar_one()
        if count:
            issues["socios_ahorro_negativo"] = count
    return issues


def upgrade(connection):
    # Una sola transacción y un lock para evitar DDL concurrente.
    connection.execute(text("SELECT pg_advisory_xact_lock(82146321)"))
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    Base.metadata.create_all(connection)
    tables = sorted(Base.metadata.tables)
    connection.execute(text('LOCK TABLE ' + ', '.join('"' + name + '"' for name in tables) + ' IN SHARE ROW EXCLUSIVE MODE'))
    issues = audit(connection)
    if issues:
        raise ValueError("Integridad inválida; migración cancelada: " + json.dumps(issues))
    # Mantener compatibilidad con instalaciones anteriores.
    connection.execute(text("ALTER TABLE notas ADD COLUMN IF NOT EXISTS fecha_programada DATE"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_notas_fecha_programada ON notas(fecha_programada)"))
    for table_name, checks in CHECKS.items():
        existing = {c["name"] for c in inspect(connection).get_check_constraints(table_name)}
        for constraint in Base.metadata.tables[table_name].constraints:
            if constraint.name in checks and constraint.name not in existing:
                connection.execute(AddConstraint(constraint))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "upgrade"])
    args = parser.parse_args()
    try:
        with engine.begin() as connection:
            if args.command == "upgrade":
                upgrade(connection)
            else:
                connection.execute(text("SET TRANSACTION READ ONLY"))
            issues = audit(connection)
            print(json.dumps({"ok": not issues, "issues": issues}, ensure_ascii=False))
            return 1 if issues else 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
