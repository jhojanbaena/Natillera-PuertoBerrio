"""Invariantes compartidas por modelos, auditoría y migración explícita."""
from sqlalchemy import CheckConstraint

# Nombres y SQL constantes; nunca se interpolan entradas de usuarios.
CHECKS = {
    "socios": {"ck_socio_aporte": "aporte_mensual >= 0"},
    "finanzas_socio": {
        "ck_finanza_monto": "monto > 0",
        "ck_finanza_tipo": "tipo_movimiento IN ('APORTE','MULTA','PAGO_MULTA','RETIRO_AHORRO')",
    },
    "actividades": {
        "ck_actividad_importes": "inversion >= 0 AND ingresos_brutos >= 0",
        "ck_actividad_ganancia": "ganancia_neta = ingresos_brutos - inversion",
    },
    "rifas": {
        "ck_rifa_boletas": "total_boletas >= 0 AND boletas_vendidas >= 0 AND boletas_vendidas <= total_boletas",
        "ck_rifa_importes": "inversion_premios >= 0 AND valor_boleta >= 0",
        "ck_rifa_tipo": "tipo IN ('INTERNA','GRANDE','PEQUENA')",
    },
    "reuniones": {"ck_reunion_ganancias": "ganancias_reunion >= 0"},
    "prestamos": {
        "ck_prestamo_importes": "monto_prestado > 0 AND tasa_interes >= 0 AND total_intereses >= 0 AND saldo_pendiente >= 0 AND saldo_pendiente <= monto_prestado",
        "ck_prestamo_cuotas": "numero_cuotas > 0 AND cuotas_pagadas >= 0",
        "ck_prestamo_estado": "estado IN ('PENDIENTE','PAGADO','EN_MORA')",
    },
    "abonos_prestamo": {
        "ck_abono_importes": "monto_abonado > 0 AND monto_capital >= 0 AND monto_interes >= 0 AND monto_abonado = monto_capital + monto_interes",
        "ck_abono_cuota": "numero_cuota > 0",
    },
}


def attach_constraints(metadata):
    for table_name, checks in CHECKS.items():
        table = metadata.tables[table_name]
        existing = {constraint.name for constraint in table.constraints}
        for name, expression in checks.items():
            if name not in existing:
                table.append_constraint(CheckConstraint(expression, name=name))
