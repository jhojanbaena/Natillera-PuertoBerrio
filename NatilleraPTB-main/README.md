# Natillera PTB

Gestión de socios, aportes, multas, préstamos, rifas, actividades, reuniones y liquidación de un fondo comunitario. Frontend React/Vite, API FastAPI y PostgreSQL.

La estructura está preparada para **Cloudflare (frontend) → Vercel (API) → Neon (PostgreSQL)**. La preparación local no crea recursos ni publica el proyecto.

## Estructura

```text
frontend/                 React, Vite, Tailwind; Cloudflare Pages o Workers Assets
backend/app/              API, modelos y reglas financieras
backend/index.py          Entrada de Vercel
backend/vercel.json       Configuración FastAPI
backend/manage_db.py      Verificación y migración explícita de esquema
backend/create_admin.py   Creación interactiva del primer administrador
backend/tests/            Pruebas aisladas SQLite/PostgreSQL
compose.yaml              PostgreSQL exclusivamente local
SECURITY_REVIEW.md        Hallazgos, correcciones, validación y pendientes
```

## Desarrollo local

Requisitos: Python **3.12+**, Node **24**, Docker Desktop u OrbStack activo.

Desde la raíz:

```bash
python3 backend/setup_local.py
docker compose --env-file backend/.env up -d --wait db
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-test.txt
python manage_db.py upgrade
python create_admin.py
python -m uvicorn app.main:app --reload --port 8000
```

En Windows activa `.venv\Scripts\activate`. Si existe `.venv`, consérvalo e instala las dependencias actualizadas. El generador conserva un `.env` existente; completa nuevas variables desde `backend/.env.example` si las necesitas.

Para una **base local nueva de demostración**, puedes usar `python seed.py` en lugar de `create_admin.py`: crea `admin / 12345678` y datos de ejemplo. El semillero está bloqueado en producción y en servidores remotos. No lo ejecutes sobre datos reales.

En otra terminal:

```bash
cd frontend
npm ci
npm run dev
```

Frontend: `http://localhost:5173`. API: `http://localhost:8000/api/v1`. Swagger local: `http://localhost:8000/docs`. El proxy de Vite conecta `/api` al puerto 8000. Para otro puerto usa `VITE_API_URL=http://localhost:8001/api/v1 npm run dev`.

La BD escucha solo en `127.0.0.1:5432`. `docker compose --env-file backend/.env down` detiene el contenedor conservando el volumen. `down -v` elimina los datos; no lo uses para reiniciar.

## Desplegar en Neon, Vercel y Cloudflare

### 1. Neon: base de datos

Crea un proyecto y separa las ramas/bases de producción y pruebas. Guarda dos conexiones desde el panel de Neon:

- **Pooled**, con `-pooler` en el hostname: para `DATABASE_URL` de Vercel.
- **Directa**, sin `-pooler`: para migración, administración y respaldo.

Usa `postgresql+psycopg2://` como prefijo para SQLAlchemy y conserva `?sslmode=require` (o `verify-full`). Codifica caracteres especiales de usuario/contraseña en la URL. Nunca agregues estas conexiones al frontend ni a Git.

Antes de modificar una base existente, crea un respaldo y comprueba su restauración en una rama separada. Ejecuta desde `backend`, con `DATABASE_URL` apuntando a la conexión **directa** y los demás ajustes configurados en tu terminal o un archivo privado:

```bash
python manage_db.py check
python manage_db.py upgrade
python manage_db.py check
python create_admin.py
```

En una base nueva, `check` informa tablas ausentes hasta ejecutar `upgrade`. En una existente, la migración valida los datos y cancela toda la transacción si detecta inconsistencias. Añade las restricciones faltantes y `notas.fecha_programada`; no borra registros ni recalcula silenciosamente información histórica. Usa una ventana sin escrituras: toma bloqueos de tabla con espera máxima de cinco segundos. Repetir `upgrade` es seguro.

Para una base poblada, `create_admin.py` se detiene si ya hay administrador. No copies el usuario de demostración a producción; utiliza credenciales propias antes de abrir el servicio.

### 2. Vercel: backend

Importa el repositorio y selecciona **Root Directory: `backend`**, framework **FastAPI**. La entrada es `index.py`; no requiere reglas heredadas de `@vercel/python`. El archivo `.python-version` selecciona Python 3.12. No ejecutes semillero ni migraciones durante el build o arranque de funciones.

Configura estas variables en Vercel, con valores distintos para Preview y Production:

| Variable | Valor |
| --- | --- |
| `ENVIRONMENT` | `production` |
| `DEBUG` | `False` |
| `AUTO_CREATE_TABLES` | `False` |
| `DATABASE_URL` | Conexión pooled de Neon con TLS |
| `SECRET_KEY` | Clave aleatoria de al menos 32 caracteres |
| `ALGORITHM` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` |
| `BACKEND_CORS_ORIGINS` | `https://TU-FRONTEND.pages.dev` o tu dominio definitivo |
| `DB_POOL_SIZE` | `2` |
| `DB_MAX_OVERFLOW` | `0` |

Genera `SECRET_KEY` de manera privada con `python -c "import secrets; print(secrets.token_hex(32))"`. No uses el valor de ejemplo. Vercel activa valores predeterminados de producción mediante `VERCEL`; aun así configura explícitamente las variables anteriores.

CORS acepta orígenes exactos separados por comas, sin `/` final, rutas ni comodines. Para previews, agrega solo las URLs que realmente necesites y utiliza una rama Neon separada. La API no crea tablas en producción y deshabilita Swagger/OpenAPI públicos. El pool limita conexiones **por instancia**, no globalmente; revisa el consumo en Neon si Vercel escala.

Después de desplegar, comprueba `https://TU-BACKEND.vercel.app/` y un login con el administrador creado. El endpoint raíz comprueba que el proceso responde; una petición autenticada que consulta datos también valida la conexión a Neon.

### 3. Cloudflare: frontend

Opción recomendada para esta SPA: **Pages**, importando el repositorio:

| Ajuste | Valor |
| --- | --- |
| Root directory | `frontend` |
| Build command | `npm run build` |
| Output directory | `dist` |
| Node | `24` |
| `VITE_API_URL` | `https://TU-BACKEND.vercel.app/api/v1` |

La URL de API es pública y se incorpora **al compilar**. Cambiarla exige recompilar. El build rechaza URLs sin HTTPS, credenciales incrustadas o rutas distintas de `/api/v1`. `public/_redirects` permite recargar rutas de React y `public/_headers` añade las cabeceras de seguridad; Vite restringe `connect-src` al origen configurado de la API.

También se conserva `frontend/wrangler.jsonc` para **Workers con Static Assets**: compila con la misma variable y despliega `dist` usando `wrangler deploy` desde `frontend`. No combines la configuración de builds de Pages y Workers en un mismo proyecto.

Una vez conocida la URL de Cloudflare, actualiza `BACKEND_CORS_ORIGINS` en Vercel y vuelve a desplegar la API. No guardes `SECRET_KEY`, `DATABASE_URL` ni contraseñas en variables `VITE_*`.

Documentación oficial utilizada: [FastAPI en Vercel](https://vercel.com/docs/frameworks/backend/fastapi), [React en Cloudflare Pages](https://developers.cloudflare.com/pages/framework-guides/deploy-a-react-site/), [conexiones Neon](https://neon.com/docs/get-started-with-neon/connect-neon).

## Seguridad e integridad

- JWT HS256 con firma, sujeto, fecha de emisión y expiración obligatorios. Bcrypt conserva hashes existentes; rechaza contraseñas de más de 72 bytes UTF-8. Nuevos registros requieren 12 caracteres mínimo.
- Registro de usuarios reservado a administradores y sin elevación de privilegios por payload. Operaciones protegidas en el servidor.
- Login limitado a diez intentos por cuenta por minuto, con contadores PostgreSQL compartidos por todas las instancias. Complementa con reglas del firewall de Vercel para limitar abuso por IP y creación masiva de cuentas inexistentes.
- Escritura de negocio y auditoría en una transacción; conflictos de integridad devuelven HTTP 409 sin detalles SQL.
- Importes de entrada limitados a la precisión de la BD; restricciones SQL para importes, tipos de movimiento, boletas y desglose de abonos.
- Reversiones rechazan cambios posteriores, IDs ocupados, dependencias y ahorros que quedarían negativos.
- La auditoría de datos comprueba restricciones, huérfanos, préstamos descuadrados y ahorro negativo. Informa cantidades sin imprimir datos personales.

El token sigue en `localStorage`: un XSS podría leerlo, y cerrar sesión no revoca un JWT ya emitido. La CSP y el saneamiento del texto enriquecido reducen exposición; no sustituyen una arquitectura con sesiones revocables. Consulta los límites y alertas pendientes en [SECURITY_REVIEW.md](SECURITY_REVIEW.md).

## Verificación

Desde `backend`:

```bash
python -m pytest -q
python run_postgres_tests.py -q
python manage_db.py check
```

SQLite usa memoria. El ejecutor PostgreSQL solo admite un servidor local y crea esquemas desechables en `natillera_test`; no borra la base de trabajo. La suite incluye validación de migración repetida, concurrencia, finanzas, autorización y atomicidad de auditoría.

Desde `frontend`:

```bash
npm ci
VITE_API_URL=https://TU-BACKEND.vercel.app/api/v1 npm run build
npm run lint
npm audit --omit=dev
npm audit
```

`npm audit` completo conserva alertas en la cadena de desarrollo de Tailwind 3. No debe interpretarse como un resultado limpio. El detalle de comprobaciones y resultados está en [SECURITY_REVIEW.md](SECURITY_REVIEW.md); los `TEST_REPORT.md` anteriores documentan revisiones históricas.

## Actualizaciones y recuperación

Mantén un respaldo recuperable antes de cada migración. Prueba primero en una rama Neon y aplica `upgrade` con conexión directa antes de desplegar código que dependa del esquema. Para revertir código, utiliza el despliegue anterior; no elimines columnas ni restricciones automáticamente. Los cambios de esquema de esta revisión son aditivos. Restaura datos únicamente desde un respaldo validado y con una ventana de mantenimiento.

La migración heredada SQLite → PostgreSQL sigue disponible en `backend/migrate_sqlite_to_postgres.py`; úsala únicamente para ese origen y sobre un destino vacío, siguiendo [backend/README.md](backend/README.md).
