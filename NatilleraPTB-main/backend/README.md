# Sistema de Gestión Integral de Natillera — Backend API

La guía vigente de despliegue **Vercel + Neon**, migraciones explícitas y controles de seguridad está en [README general](../README.md) y [SECURITY_REVIEW.md](../SECURITY_REVIEW.md). En producción usa `AUTO_CREATE_TABLES=False`; ejecuta `python manage_db.py upgrade` antes de desplegar y crea el administrador con `python create_admin.py`. El semillero solo admite PostgreSQL local.

Backend robusto, modular y escalable para la administración completa de una **Natillera** (Fondo comunitario de ahorro y crédito), desarrollado con **FastAPI**, **SQLAlchemy 2.0**, **Pydantic v2**, **PostgreSQL** y seguridad basada en **JWT** con **Bcrypt**.

---

## 🚀 Arquitectura y Stack Tecnológico

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.12+) con OpenAPI automático y Swagger UI.
- **ORM**: [SQLAlchemy 2.0](https://www.sqlalchemy.org/) con tipado estricto `Mapped` y `mapped_column`.
- **Validación y DTOs**: [Pydantic v2](https://docs.pydantic.dev/) con `ConfigDict(from_attributes=True)`.
- **Seguridad**: JSON Web Tokens (`PyJWT` HS256) y cifrado de contraseñas con `bcrypt`.
- **Manejo Financiero Exacto**: Uso de `Numeric(12, 2)` / `Decimal` en todos los valores monetarios para evitar distorsiones de redondeo de punto flotante.
- **Base de Datos**: PostgreSQL, configurada mediante `DATABASE_URL` en `.env`.

---

## 📁 Estructura del Backend

```text
backend/
├── .env                              # Variables de entorno activas
├── .env.example                      # Plantilla de configuración PostgreSQL
├── requirements.txt                  # Dependencias de Python
├── migrate_sqlite_to_postgres.py     # Migración de datos desde la base SQLite anterior
├── seed.py                           # Semillero de datos iniciales
└── app/
    ├── __init__.py
    ├── main.py                       # Punto de entrada FastAPI, CORS y ciclo de vida
    ├── core/                         # Núcleo de la aplicación (config, database, security, deps)
    ├── models/                       # Modelos ORM Relacionales (SQLAlchemy)
    ├── schemas/                      # DTOs y Esquemas de validación (Pydantic v2)
    ├── services/                     # Servicios de negocio y agregaciones complejas
    └── routers/                      # Controladores RESTful (/auth, /socios, /prestamos, etc.)
```

---

## ⚙️ Instalación y Puesta en Marcha

### 1. Acceder al directorio del backend
```bash
cd backend
```

### 2. Crear y activar el entorno virtual
En Windows:
```powershell
python -m venv .venv
.venv\Scripts\activate
```
En Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Crear y configurar PostgreSQL con Docker

Con Docker Desktop u OrbStack iniciado, ejecuta desde `backend`:

```bash
python setup_local.py
docker compose -f ../compose.yaml --env-file .env up -d --wait db
```

`setup_local.py` genera `.env` desde `.env.example`, con clave JWT y contraseña
PostgreSQL aleatorias. Conserva cualquier `.env` existente; si está incompleto,
rellena `DATABASE_URL`, `SECRET_KEY` y las variables `POSTGRES_*` usando la plantilla.
El archivo contiene credenciales locales y está excluido de Git. No publiques su contenido.

Compose ejecuta PostgreSQL 17, con healthcheck y volumen persistente. El servicio
escucha en `127.0.0.1:5432`; `DATABASE_URL` usa el driver `postgresql+psycopg2`.
Si ese puerto está ocupado, cambia `POSTGRES_PORT` y el puerto de `DATABASE_URL`
al mismo valor libre antes de levantar la base.

Para consultar el estado, abrir una consola SQL o detenerla sin borrar datos:

```bash
docker compose -f ../compose.yaml --env-file .env ps
docker compose -f ../compose.yaml --env-file .env exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
docker compose -f ../compose.yaml --env-file .env down
```

El volumen `natillera-local_postgres_data` persiste entre arranques. `down -v`
lo eliminaría junto con sus datos. Las credenciales `POSTGRES_*` solo inicializan
volúmenes nuevos: cambiar `.env` no cambia usuarios de una BD existente.

Si ya tienes PostgreSQL, configura su URL en `.env` y omite Docker. La aplicación
carga `backend/.env` por ruta absoluta; las variables del proceso tienen prioridad.
SQLite y MySQL no se admiten como base de la aplicación.

### 5. Migrar los datos SQLite existentes (si aplica)

Si necesitas conservar los datos del archivo `natillera.db`, migra antes de iniciar el backend. El destino debe estar vacío:

```bash
python migrate_sqlite_to_postgres.py
```

El script verifica las tablas y columnas, copia los registros respetando las relaciones, reajusta las secuencias y conserva el archivo SQLite original como respaldo. No ejecutes `seed.py` si ya migraste datos.

### 6. Semillero de Datos (Opcional)
Para inicializar la base de datos con datos de prueba (usuario admin `admin / 12345678`, socios, préstamos, etc.):
```bash
python seed.py
```

### 7. Iniciar el servidor de desarrollo
```bash
python -m uvicorn app.main:app --reload --port 8000
```
La aplicación estará disponible en `http://localhost:8000`. Para probarla:

```bash
curl http://127.0.0.1:8000/
curl -X POST http://127.0.0.1:8000/api/v1/auth/login-json -H 'Content-Type: application/json' -d '{"username":"admin","password":"12345678"}'
```

El login anterior requiere haber ejecutado `python seed.py` en la base local nueva.
Utiliza el token obtenido en **Authorize** de Swagger para probar las rutas protegidas.

Si el puerto 8000 está ocupado (`Address already in use`), usa
`python -m uvicorn app.main:app --reload --port 8001` y abre
`http://localhost:8001/docs`. Para probar también el frontend desde macOS/Linux,
ejecuta `VITE_API_URL=http://localhost:8001/api/v1 npm run dev` en `frontend`.

Si aparece `DATABASE_URL: Field required`, falta `.env` o su URL: ejecuta
`python setup_local.py` y revisa el archivo si ya existía. Si falla la conexión,
comprueba que el servicio `db` esté saludable y que la URL coincida con `POSTGRES_*`.

---

## 📖 Documentación Interactiva (Swagger / OpenAPI)

Una vez iniciado el servidor:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Pruebas locales

Desde `backend`, con un entorno virtual activo:

```bash
pip install -r requirements-test.txt
python -m pytest -q --cov=app --cov-report=term-missing
```

Las pruebas por defecto usan SQLite en memoria con claves foráneas habilitadas.
Sustituyen la sesión de datos y no ejecutan el ciclo de arranque de la aplicación.

Para verificar también PostgreSQL y los bloqueos de retiros, con Docker activo:

```bash
# Desde backend; el contenedor debe estar levantado.
docker compose -f ../compose.yaml --env-file .env up -d --wait db
python run_postgres_tests.py -q --cov=app --cov-report=term
```

El ejecutor lee únicamente la URL local de `.env`, crea `natillera_test` si no
existe y utiliza un esquema aleatorio por caso. Cada esquema se elimina al
terminar su prueba. No ejecuta pruebas sobre `natillera_db` ni sus datos de
demostración. Requiere instalar `requirements-test.txt` y un usuario local con
permiso para crear esa base y los esquemas.

Resultado del 21 de octubre de 2026: **64 pruebas aprobadas en PostgreSQL**, con
**86% de cobertura de sentencias**. En SQLite pasan 63 y se omite la prueba de
concurrencia que requiere PostgreSQL. Los seis defectos iniciales están corregidos.

## Reglas corregidas

- La liquidación reparte las ganancias netas de actividades, rifas y reuniones
  proporcionalmente al ahorro, conservando los centavos. Las multas y los intereses
  desde la cuarta cuota se reparten como bien común; los intereses de las tres
  primeras cuotas ya están en el ahorro personal y no se vuelven a repartir.
  Si no hay ahorro positivo, no se asignan utilidades proporcionales.
- Un préstamo solo queda `PAGADO` al cubrir capital e intereses. Se admiten abonos
  solo de intereses cuando el capital ya está cubierto. Crear, editar o revertir
  abonos recalcula saldo, cuotas y estado.
- Las nuevas eliminaciones de socios guardan préstamos, abonos, movimientos y
  fechas para su restauración. Un ID reutilizado produce HTTP 409 sin sobrescribirlo.
  Los historiales antiguos que no guardaron préstamos no permiten reconstruirlos.
- Los retiros no pueden superar aportes menos retiros anteriores: devuelven HTTP
  422 sin guardar el movimiento. PostgreSQL bloquea al socio durante la operación
  para evitar que dos retiros simultáneos consuman el mismo saldo.
- Crear o editar una rifa exige que las boletas vendidas no superen las emitidas,
  incluyendo ediciones de un solo campo. Se devuelve HTTP 422 si se incumple.
- Editar un abono genera historial `EDITAR` en la misma transacción; su reversión
  restaura los importes y recalcula el préstamo. Cambios posteriores incompatibles
  producen HTTP 409, sin sobrescribirlos.

No se requieren migraciones ni dependencias nuevas para las correcciones. No se
ha ejecutado una recalculación masiva de datos históricos. Consulta
[TEST_REPORT.md](TEST_REPORT.md) para resultados, límites y comandos.
