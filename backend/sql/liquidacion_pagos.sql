-- Control de pagos de la Liquidación anual (Supabase / PostgreSQL).
-- Idempotente: se puede ejecutar varias veces en el SQL Editor de Supabase.
-- Equivale a lo que crea `python manage_db.py upgrade` o el arranque con AUTO_CREATE_TABLES.

BEGIN;

CREATE TABLE IF NOT EXISTS liquidacion_fondos (
    id SERIAL PRIMARY KEY,
    anio INTEGER NOT NULL,
    monto_general NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ,
    CONSTRAINT ck_liquidacion_fondo_monto CHECK (monto_general >= 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_liquidacion_fondos_anio ON liquidacion_fondos (anio);

CREATE TABLE IF NOT EXISTS liquidacion_pagos (
    id SERIAL PRIMARY KEY,
    anio INTEGER NOT NULL,
    socio_id INTEGER NOT NULL REFERENCES socios(id) ON DELETE CASCADE,
    nombre_socio VARCHAR(150) NOT NULL,
    monto NUMERIC(14, 2) NOT NULL,
    metodo_pago VARCHAR(20) NOT NULL,
    fecha_pago TIMESTAMPTZ NOT NULL DEFAULT now(),
    usuario_nombre VARCHAR(100),
    -- Un socio solo puede liquidarse una vez por año (evita duplicados aun en concurrencia).
    CONSTRAINT uq_liquidacion_pago_anio_socio UNIQUE (anio, socio_id),
    CONSTRAINT ck_liquidacion_pago_monto CHECK (monto >= 0),
    CONSTRAINT ck_liquidacion_pago_metodo CHECK (metodo_pago IN ('EFECTIVO', 'TRANSFERENCIA'))
);
CREATE INDEX IF NOT EXISTS ix_liquidacion_pagos_anio ON liquidacion_pagos (anio);
CREATE INDEX IF NOT EXISTS ix_liquidacion_pagos_socio_id ON liquidacion_pagos (socio_id);

COMMIT;
