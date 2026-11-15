# Correcciones y pruebas del backend

Fecha: 21 de octubre de 2026.

## Resultado actual

**Los seis defectos reproducidos están corregidos.**

| Entorno | Resultado |
| --- | --- |
| PostgreSQL 17 en Docker, base `natillera_test` | 64 aprobadas, cero fallidas |
| SQLite en memoria | 63 aprobadas, una omitida (retiros concurrentes) |
| Cobertura de sentencias `app` en PostgreSQL | 86%: 1.500 de 1.740 sentencias |
| Limpieza tras las pruebas PostgreSQL | Cero esquemas de prueba restantes |
| Base de demostración | Conserva sus cinco socios |

Antes de las correcciones, la suite original reproducía seis fallos (42 casos
aprobados de 48). Los casos nuevos reprodujeron otros ocho fallos relacionados
antes de aplicar los cambios. Los tests no se deshabilitaron ni se marcaron
`xfail` para ocultar defectos. La única omisión en SQLite requiere bloqueo de
filas y se ejecutó satisfactoriamente en PostgreSQL.

## Cambios y trazabilidad

| Defecto | Corrección | Regresión principal |
| --- | --- | --- |
| Liquidación sin utilidades | Reparte ganancias de actividades, rifas y reuniones según ahorro; evita duplicar los intereses personales o el bien común. Distribución por restos mayores para conservar centavos. | `test_liquidation_distributes_activity_profit`, `test_liquidation_preserves_all_funds_without_double_interest`, `test_liquidation_proportional_profit_and_cent_conservation` |
| Préstamos pagados con intereses pendientes | Servicio común recalcula capital, cuotas y estado; `PAGADO` exige cubrir intereses. Permite cancelar intereses con capital pendiente cero. | `test_loan_remains_open_until_interest_is_paid`, `test_interest_only_final_payment_and_undo`, `test_zero_interest_loan_closes_on_capital_payment` |
| Socio restaurado sin préstamos | La instantánea incluye préstamos con abonos y finanzas. La restauración respeta IDs, importes y fechas, inserta padres antes que hijos y rechaza IDs ocupados. | `test_deleted_socio_restore_keeps_loans`, `test_restore_socio_keeps_loan_payments_and_dates`, `test_restore_does_not_overwrite_reused_socio_id` |
| Retiros sin fondos | Compara con aportes menos retiros antes de insertar; bloquea la fila del socio hasta confirmar movimiento e historial. HTTP 422 si no hay fondos. | `test_rejects_withdrawal_exceeding_savings`, `test_withdrawal_exact_balance_then_reject_extra`, `test_concurrent_withdrawals_do_not_overdraw_postgres` |
| Sobreventa de boletas | Valida creación y estado final de edición parcial antes de aplicar cambios. HTTP 422 si vendidas supera emitidas. | `test_rejects_oversold_raffle`, `test_raffle_partial_edit_validates_combined_state` |
| Edición de abonos sin reversión | Guarda `EDITAR` y préstamo en una misma transacción. Reversión restaura importes y recalcula préstamo; HTTP 409 ante cambios posteriores incompatibles. | `test_payment_edit_can_be_reverted`, `test_edit_payment_undo_restores_interest_and_status`, `test_payment_edit_rollback_when_audit_fails`, `test_payment_undo_rejects_stale_edit_then_allows_latest_first`, `test_undo_edit_cannot_overpay_after_later_payment` |

Se mantiene la regla existente: intereses de las primeras tres cuotas se suman
al ahorro personal; multas pagadas e intereses desde la cuarta cuota integran el
bien común. Las utilidades de actividades, rifas y reuniones se reparten aparte.
Si todos los ahorros son cero, no se asignan utilidades proporcionales. Las
pérdidas se distribuyen con el mismo criterio y los centavos residuales siguen
un orden estable por nombre e ID.

La reversión de un pago solo de intereses reabre el préstamo aunque el capital
siga en cero. Los cálculos consultan abonos persistidos tras `flush`, evitando
usar colecciones ORM desactualizadas al crear o eliminar un abono.

La prueba concurrente dispara dos retiros de 100 con ahorro total de 100:
PostgreSQL acepta uno con HTTP 201 y rechaza el otro con HTTP 422. Solo se
almacena un retiro y el saldo queda en cero.

## Archivos afectados

- `app/services/finanzas_service.py`: reparto financiero y conciliación de centavos.
- `app/services/prestamos_service.py`: recálculo compartido de préstamos.
- `app/routers/prestamos.py`: abonos, bloqueo del préstamo e historial de edición.
- `app/services/historial_service.py`: instantáneas completas, restauración y reversión de abonos.
- `app/routers/socios.py`: disponibilidad de ahorro, bloqueo y confirmación conjunta con historial.
- `app/schemas/rifa.py`, `app/routers/rifas.py`: validación de boletas.
- `tests/test_financial_regressions.py`: casos límite y concurrencia.
- `tests/conftest.py`, `run_postgres_tests.py`: ejecución aislada en PostgreSQL local.
- README de raíz y backend; actualización del estado en el informe frontend.

No hay migraciones de esquema ni dependencias nuevas. Se conserva la arquitectura
FastAPI/SQLAlchemy, las rutas y los formatos de respuesta. Las nuevas restricciones
HTTP 422 y 409 documentan los rechazos de las operaciones inválidas.

## Reproducción

Desde `backend`, con un entorno virtual activo:

```bash
python -m pip install -r requirements-test.txt
# Pruebas rápidas, sin Docker ni conexiones externas:
python -m pytest -q --tb=short

# Integración con PostgreSQL local:
docker compose -f ../compose.yaml --env-file .env up -d --wait db
python run_postgres_tests.py -q --cov=app --cov-report=term --tb=short
```

El ejecutor lee la URL de `backend/.env`, exige loopback y crea la base local
`natillera_test` si no existe. La fixture permite PostgreSQL solo en esa base.
Cada caso recibe un esquema aleatorio y lo elimina al terminar. No se usa el
esquema público ni la base de demostración para los datos de prueba.

Validación realizada con Python 3.14.3, FastAPI 0.156.4, SQLAlchemy 2.1.5,
Pydantic 2.14.1, pytest 9.1.1 y PostgreSQL 17. La suite conserva un aviso de
Starlette sobre deprecación del uso de httpx en TestClient; no impide la ejecución.

## Límites y datos anteriores

Las eliminaciones anteriores cuya instantánea no guardó préstamos o abonos no
permiten reconstruir los datos perdidos. Las nuevas eliminaciones sí los guardan.
No se ejecutó una recalculación masiva de préstamos ni otra modificación de
registros históricos. Al registrar o editar abonos se recalcula el préstamo
involucrado, incluyendo un estado antiguo incorrecto si todavía debe intereses.

La liquidación sigue siendo acumulada, sin filtro por año, y mantiene la selección
de socios existente. No se introdujo una regla nueva de periodos o elegibilidad.
La cobertura no constituye una auditoría contable exhaustiva. El servicio de
historial alcanza 61% de cobertura: quedan ramas de otros tipos de reversión sin
probar. La atomicidad se reforzó en abonos y movimientos de socios; otras escrituras
existentes todavía pueden confirmar datos e historial en transacciones distintas.

Estas pruebas HTTP usan TestClient con sesiones PostgreSQL reales; no ejecutan el
lifespan productivo ni validan cambios automáticos de compatibilidad de columnas.
No se repitieron los flujos de navegador ni se hicieron pruebas de carga o
migraciones. La prueba de login frontend de la revisión anterior sigue documentada
en `frontend/TEST_REPORT.md`.
