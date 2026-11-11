# Revisión de seguridad e integridad

Fecha: **21 de octubre de 2026**, zona America/Bogota.

Alcance: código local FastAPI/React, dependencias instaladas, datos PostgreSQL locales y preparación para Cloudflare/Vercel/Neon. No se accedió a cuentas cloud ni se publicó la aplicación. Esta carpeta no contiene `.git`: no se pudo revisar historial de commits ni secretos que pudieran existir en él.

## Hallazgos corregidos

| Riesgo | Evidencia e impacto | Corrección y comprobación |
| --- | --- | --- |
| Alto: auditoría separada del cambio | Altas y ediciones hacían `commit` antes de registrar historial; un fallo posterior dejaba datos sin bitácora. | `flush` seguido de un único commit con la auditoría. Prueba de fallo simulado confirma rollback. |
| Alto: truncamiento de contraseña | Bcrypt recibía solo los primeros 72 bytes; distintas contraseñas podían validarse con el mismo prefijo. | Rechazo de exceso de bytes, incluido UTF-8 multibyte. Hashes existentes compatibles; contraseñas largas antiguas requieren cambio. |
| Alto: reversiones inseguras | Restauraciones con `merge` podían sobrescribir IDs reutilizados; revertir un aporte podía dejar ahorro negativo. | Inserción con rechazo de IDs ocupados, comprobación de instantánea, dependencias y saldo. Casos automatizados. |
| Medio: bibliotecas JWT con avisos | La auditoría detectó avisos en `python-jose` y su dependencia `ecdsa`; la configuración HS256 reducía la exposición a los vectores asimétricos, pero los paquetes seguían presentes. | Sustitución por PyJWT, algoritmo permitido fijo y claims `exp`, `iat`, `sub` obligatorios; eliminación de bibliotecas sin uso. |
| Medio: intentos de login sin límite | Ambos endpoints aceptaban intentos sin contador compartido. | Máximo diez por cuenta/minuto, persistido con upsert PostgreSQL atómico; funciona entre instancias y entre ambos endpoints. Verificación dummy ante usuario inexistente. |
| Medio: integridad solo en aplicación | Faltaban CHECK SQL y límites de precisión para importes; escrituras directas podían omitir validaciones. | Restricciones compartidas por modelos/migración y validación Decimal con precisión de la BD. Pruebas de inserción inválida y valores no finitos. |
| Medio: DDL en cada arranque | `create_all` y cambios de compatibilidad se ejecutaban al iniciar la API. | Migración explícita e idempotente; producción bloquea creación automática, DEBUG y conexiones sin TLS. |
| Medio: dependencias frontend | `npm audit` inicial: 10 alertas (8 altas y 2 moderadas). | Actualización compatible de 9 paquetes; Vite 8.3.5 y transitivas corregidas. Permanecen 7 alertas de desarrollo detalladas abajo. |
| Medio: pegado de HTML enriquecido | El editor permitía al navegador insertar contenido del portapapeles antes del saneamiento posterior. | Sanea HTML antes de insertarlo y bloquea arrastre de contenido. Revisión de código y compilación; falta prueba específica de navegador. |
| Bajo: exposición y configuración | Headers ausentes, documentación pública por defecto y riesgo de publicar secretos locales. | CSP de frontend con origen API exacto, no-store en API, CORS explícito, docs deshabilitados en producción, `.vercelignore`, ejemplos y exclusiones de secretos. |

Además, usuarios nuevos del modelo tienen `is_admin=False` por defecto. El endpoint de registro continúa reservado a administradores y crea usuarios sin permisos administrativos. El semillero con contraseña conocida solo admite PostgreSQL local; el primer administrador de producción se crea interactivamente.

## Integridad de la base local

La auditoría de solo lectura inicial no encontró incumplimientos financieros en las reglas revisadas; informó únicamente la nueva tabla `login_limits` ausente. No se corrigieron ni reescribieron importes históricos.

Se generó un respaldo PostgreSQL custom **dentro del contenedor local** en `/tmp/natillera-before-security.dump`; `pg_restore --list` confirmó que el archivo es legible. **No se ensayó una restauración completa**. Ese archivo no es un respaldo permanente fuera del contenedor.

Después se ejecutaron `manage_db.py upgrade` y `manage_db.py check` sobre la base local. Ambos finalizaron con `{"ok": true, "issues": {}}`. La migración añade la tabla de login y restricciones sin borrar filas. Comprueba:

- Importes, tipos de movimientos, estados y cantidades de boletas.
- Desglose de abonos: monto = capital + interés.
- Relaciones huérfanas de las claves foráneas modeladas.
- Capital abonado, saldo, número de abonos y préstamos marcados pagados con deuda.
- Socios con retiros superiores a aportes.

Estas comprobaciones no equivalen a una conciliación contable con extractos externos, ni reconstruyen auditoría ausente en registros anteriores. Invariantes entre varias filas dependen también de los servicios y bloqueos de la aplicación; no todas están implementadas como restricciones SQL.

La migración usa una transacción, lock asesor, bloqueos de tablas y `lock_timeout=5s`. Se probó dos veces sobre esquemas PostgreSQL poblados y desechables. No hay migración destructiva de rollback; si falla, PostgreSQL revierte la transacción. Para una base grande se debe medir la duración del escaneo y planificar una ventana sin escrituras.

## Dependencias y riesgo pendiente

| Comprobación | Resultado |
| --- | --- |
| `pip-audit` del entorno Python tras correcciones | 0 avisos conocidos, 64 paquetes auditados |
| `pip check` | Sin incompatibilidades de requisitos |
| `npm audit --omit=dev` | 0 vulnerabilidades conocidas |
| `npm audit` completo | 7 alertas: 5 altas, 2 moderadas; todas en cadena de desarrollo de Tailwind 3 |

Las alertas restantes afectan `braces`, `chokidar`, `micromatch`, `fast-glob`, `postcss-selector-parser`, `postcss-nested` y `tailwindcss`. Son avisos de la cadena de compilación y no se incluyen como servidor Node en el frontend estático desplegado. Debe evitarse procesar CSS, patrones o mapas de fuentes no confiables durante builds.

Avisos raíz: [braces: agotamiento de pila](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) y [PostCSS selector parser: complejidad cuadrática](https://github.com/advisories/GHSA-rj75-hqrm-r3gf). npm propone migrar a Tailwind 4; no se aplicó ese cambio mayor porque requiere adaptar y validar los estilos visualmente. No se afirma que el árbol completo esté libre de vulnerabilidades.

Riesgos residuales:

- JWT en `localStorage`; cerrar sesión no revoca tokens emitidos. La expiración predeterminada es 60 minutos, pero una configuración existente puede conservar 480.
- El límite por cuenta no impide ataques distribuidos sobre muchos nombres y permite agotar temporalmente los intentos de una cuenta. Antes de publicar, complementar con firewall/rate limit por IP en Vercel; CORS no sustituye autenticación ni firewall.
- Los contadores expiran por ventana y se depuran durante logins; no existe una infraestructura externa de bloqueo global de tráfico.
- No se auditó IAM, dominios, configuración de cuentas, backups/PITR de Neon ni tráfico real de producción.
- Dependencias Python directas fijadas; el resultado de auditoría corresponde al entorno instalado. Revisar dependencias transitivas en cada despliegue. No se validó instalación nueva de Python 3.12 aquí: las pruebas locales usaron Python 3.14.
- No se hizo una prueba nueva de navegador del login o de XSS en esta revisión. Las pruebas de navegador documentadas en `frontend/TEST_REPORT.md` son históricas.

## Puertas de calidad

| Área | Estado | Evidencia |
| --- | --- | --- |
| API y reglas financieras, SQLite | verified | 77 aprobadas; 2 omitidas por requerir PostgreSQL |
| API, concurrencia y migración PostgreSQL | verified | 79 aprobadas en esquemas aislados de `natillera_test` |
| Integridad local posterior a migración | verified | `manage_db.py check`: sin incidencias |
| Compilación frontend | verified | Vite 8.3.5; URL HTTPS configurada; `_headers` y `_redirects` en `dist` |
| Lint frontend | verified | Código de salida 0; conserva advertencias de React/imports existentes |
| Auditorías de dependencias | verified | Resultados y límites indicados arriba |
| Recuperación completa del respaldo | not_verified | Solo se comprobó lectura del archivo |
| Pipeline GitHub Actions | not_verified | Archivo preparado, no ejecutado en GitHub |
| Despliegue Cloudflare/Vercel/Neon | not_verified | Configuración y pasos preparados; sin despliegue remoto |
| Publicación y credenciales productivas | not_applicable | No se crearon recursos ni se rotaron credenciales |

La suite emite un aviso de deprecación de Starlette/TestClient sobre `httpx`; no afecta el resultado de las pruebas. La configuración cloud sigue documentación oficial de [Vercel](https://vercel.com/docs/frameworks/backend/fastapi), [Cloudflare Pages](https://developers.cloudflare.com/pages/framework-guides/deploy-a-react-site/) y [Neon](https://neon.com/docs/get-started-with-neon/connect-neon).
