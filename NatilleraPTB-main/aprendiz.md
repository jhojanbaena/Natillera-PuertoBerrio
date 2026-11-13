# Guía del aprendiz: desplegar Natillera PTB desde un archivo ZIP

Esta guía te acompaña desde el ZIP entregado por el instructor hasta tener la aplicación funcionando en Internet con tus propias cuentas:

- **GitHub:** guarda tu copia del código.
- **Neon:** aloja la base de datos PostgreSQL.
- **Vercel:** ejecuta el backend, que es la API escrita en Python/FastAPI.
- **Cloudflare Pages:** publica el frontend, que es la interfaz escrita en React/Vite.

No necesitas que el instructor publique el proyecto en su GitHub. Tú crearás tu repositorio y conectarás ese mismo repositorio a Vercel y Cloudflare. Tampoco necesitas Docker ni instalar un servidor PostgreSQL en tu equipo para seguir esta guía: usarás Neon directamente.

**Lee y ejecuta los pasos en orden.** Los textos `TU-USUARIO`, `TU-BACKEND`, `TU-FRONTEND`, `REEMPLAZAR...` y las conexiones mostradas son ejemplos: debes sustituirlos por tus valores. No escribas los símbolos de la terminal ni las etiquetas de los bloques; copia solamente los comandos.

Los nombres de algunos menús pueden aparecer en inglés o cambiar de ubicación. Esta guía se preparó el **22 de octubre de 2026**, tomando como referencia el código entregado y la documentación oficial enlazada en cada etapa.

## 1. Entender qué vas a conectar

```text
Tu navegador
    │
    ▼
Frontend: https://TU-FRONTEND.pages.dev
    │ Peticiones a /api/v1
    ▼
Backend: https://TU-BACKEND.vercel.app
    │ Conexión privada a PostgreSQL
    ▼
Base de datos en Neon
```

Una **base de datos** es el contenedor de la información. Las **tablas o entidades** son las estructuras que guardan usuarios, socios, préstamos y demás registros. Crear el proyecto en Neon no crea las tablas de esta aplicación: las crearás expresamente en el paso 5.

Una **variable de entorno** es un ajuste que proporcionas a un programa, por ejemplo la dirección de la base de datos. Un **despliegue** es una versión del programa publicada en una plataforma. Un **commit** guarda una versión de tus archivos en Git; un **push** la envía a GitHub.

## 2. Preparar tu equipo y abrir el ZIP

### 2.1. Crear las cuentas e instalar las herramientas

Necesitas acceso a Internet, una terminal y estas herramientas:

| Herramienta o cuenta | Qué debes hacer |
| --- | --- |
| [GitHub](https://github.com/) | Crear tu cuenta e iniciar sesión. |
| [Neon](https://console.neon.tech/) | Crear una cuenta; puedes usar tu acceso de GitHub. |
| [Vercel](https://vercel.com/) | Crear una cuenta; puedes usar tu acceso de GitHub. |
| [Cloudflare](https://dash.cloudflare.com/) | Crear una cuenta e iniciar sesión. |
| [Visual Studio Code](https://code.visualstudio.com/) | Instalarlo para editar archivos y abrir la terminal. |
| [Git](https://git-scm.com/downloads) | Instalarlo para subir el código a tu repositorio. |
| [Python](https://www.python.org/downloads/) | Instalar **Python 3.12** para usar la misma versión indicada en `backend/.python-version`. En Windows, habilita la opción de agregar Python al `PATH` si aparece. |
| [Node.js](https://nodejs.org/en/download) | Instalar la versión **24**; incluye `npm`. El proyecto la declara en `frontend/.node-version`. |

Consulta los límites y condiciones del plan que elijas en cada servicio. No necesitas comprar un dominio para este recorrido: usarás las direcciones que generan las plataformas.

### 2.2. Descomprimir y abrir la carpeta correcta

1. Guarda el ZIP en tu equipo.
2. Usa **Extraer todo** en Windows o descomprímelo en macOS/Linux. No trabajes dentro del ZIP.
3. Abre VS Code y elige **Archivo → Abrir carpeta**.
4. Selecciona la carpeta que contiene directamente `backend`, `frontend` y `README.md`. A esta carpeta la llamaremos **raíz del proyecto**.
5. Abre **Terminal → Nueva terminal**.

Debes ver una estructura similar a esta; algunos archivos empiezan por punto y pueden estar ocultos en el explorador:

```text
NatilleraPTB-main/
├── .gitignore
├── aprendiz.md
├── README.md
├── backend/
│   ├── .env.example
│   ├── .python-version
│   ├── requirements.txt
│   ├── manage_db.py
│   ├── create_admin.py
│   ├── index.py
│   ├── vercel.json
│   └── app/
└── frontend/
    ├── .env.example
    ├── .node-version
    ├── package.json
    ├── package-lock.json
    ├── public/
    └── src/
```

Si ves otra carpeta `NatilleraPTB-main` dentro de la que abriste, entra en ella: necesitas abrir la que contiene directamente `backend` y `frontend`.

### 2.3. Comprobar las herramientas

En la terminal de VS Code ejecuta, una línea a la vez:

```text
git --version
node --version
npm --version
```

Node debe mostrar `v24...`. Para Python, en **Windows** ejecuta:

```powershell
py -3.12 --version
```

En **macOS/Linux**:

```bash
python3.12 --version
```

Python debe mostrar `3.12...`. Si un comando no se reconoce, termina la instalación correspondiente y cierra y vuelve a abrir VS Code para que detecte el `PATH` actualizado.

## 3. Subir tu propia copia a GitHub

### 3.1. Revisar qué se puede subir

El archivo `.gitignore` ya excluye las credenciales, los entornos virtuales, las bases locales y las dependencias instaladas. Consérvalo en la raíz.

**No publiques** archivos `.env`, contraseñas, conexiones de Neon, claves JWT, archivos de bases de datos ni respaldos. Si el ZIP contiene `.env`, no reutilices credenciales del instructor: en el paso 5 prepararás las tuyas. Tampoco reutilices una carpeta `.venv` de otro equipo.

Sí debes subir `.env.example`, `.python-version`, `.node-version`, `package-lock.json`, el código y las configuraciones del proyecto. Los archivos de ejemplo deben seguir conteniendo únicamente valores de ejemplo.

### 3.2. Crear un repositorio vacío en tu cuenta

1. Entra a GitHub y pulsa **+ → New repository**.
2. Escribe un nombre, por ejemplo `natillera-aprendiz`.
3. Puedes seleccionar **Private**. Después darás acceso a Vercel y Cloudflare a ese repositorio.
4. Deja desactivadas las opciones de agregar README, `.gitignore` o licencia: ya tienes archivos locales y necesitas un repositorio vacío.
5. Pulsa **Create repository**.
6. Copia su dirección HTTPS, similar a `https://github.com/TU-USUARIO/natillera-aprendiz.git`.

Referencia: [crear un repositorio en GitHub](https://docs.github.com/en/get-started/start-your-journey/creating-a-repository-for-your-project-on-github).

### 3.3. Preparar la primera versión local

En la terminal, **desde la raíz del proyecto**, configura tu nombre y correo. Sustituye los ejemplos; estos datos identifican tus commits y no son tu contraseña:

```bash
git init
git config user.name "Tu Nombre"
git config user.email "tu-correo@example.com"
git branch -M main
git add .
git status
```

**Antes de continuar**, revisa la lista de archivos que muestra `git status`. Deben aparecer `backend/`, `frontend/` y los documentos del proyecto. No deben aparecer `.env`, `node_modules/`, `.venv/` ni bases de datos. Si aparecen, detente y revisa que `.gitignore` esté en la raíz antes de crear el commit.

Cuando la lista sea correcta:

```bash
git commit -m "Agregar proyecto Natillera PTB"
git remote add origin https://github.com/TU-USUARIO/natillera-aprendiz.git
git push -u origin main
```

Usa tu dirección real de GitHub en `git remote add`. Si Git solicita autenticación, completa el acceso en el navegador mediante el gestor de credenciales. GitHub no acepta la contraseña normal de la cuenta como contraseña de Git por HTTPS; si necesitas ayuda, consulta [autenticación en GitHub](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github).

Si aparece `remote origin already exists`, ejecuta `git remote -v`. Si apunta a otra dirección, cámbiala a tu repositorio con:

```bash
git remote set-url origin https://github.com/TU-USUARIO/natillera-aprendiz.git
git push -u origin main
```

Si Git informa que ya existía un repositorio al hacer `git init`, revisa `git log --oneline -5` y `git remote -v` antes de publicar: confirma que no estés enviando un historial ajeno con secretos. Un ZIP de entrega sin historial evita esta situación.

Abre tu repositorio en GitHub y verifica que **en su raíz** aparezcan `backend` y `frontend`. No subas el ZIP como un único archivo: las plataformas necesitan acceder al código descomprimido.

## 4. Crear la base de datos en Neon

### 4.1. Crear un proyecto y elegir su base

1. Entra a [la consola de Neon](https://console.neon.tech/).
2. Elige **New project** o **Create project**.
3. Ponle un nombre, por ejemplo `natillera-aprendiz`.
4. Selecciona una región cercana a la región donde ejecutarás el backend. Si todavía no la conoces, anota la región elegida para buscar una ubicación cercana en Vercel.
5. Si permite elegir PostgreSQL, puedes usar **17**, la versión que usa el entorno local de este proyecto.
6. Completa **Create project**.
7. Entra en **Branches** y anota el nombre de la rama creada. Puede ser `production`, `main` u otro nombre indicado en tu panel. Aquí la llamaremos **tu rama de producción**; usa siempre la misma durante este primer despliegue.
8. Busca la sección **Databases** de esa rama. Neon suele crear una base llamada `neondb` y un rol propietario, por ejemplo `neondb_owner`.

**Para esta guía puedes usar `neondb` tal como está.** Esa es tu base de datos PostgreSQL, aunque no se llame igual que el proyecto. Por ahora estará vacía de tablas de Natillera.

Si prefieres llamarla `natillera_db`, usa **Databases → New database / Create database** en la rama elegida, escribe `natillera_db`, selecciona el rol propietario y confirma. Desde ese momento elige `natillera_db` en todas las conexiones y en el editor SQL. No necesitas crear las dos bases para seguir la guía.

Un **rol de PostgreSQL** permite conectarse a la base; es distinto del usuario administrador con el que entrarás a la aplicación. No necesitas habilitar **Neon Auth**: este proyecto ya tiene su propio inicio de sesión.

Referencias: [consola y creación del proyecto](https://neon.com/docs/get-started/signing-up), [administrar bases de datos](https://neon.com/docs/manage/databases).

### 4.2. Obtener dos conexiones a la misma base

Una conexión es una dirección que contiene usuario, contraseña, servidor y nombre de base. Trátala como una contraseña.

1. Pulsa **Connect** en Neon.
2. Selecciona tu rama de producción, su **Compute**, la base elegida (`neondb` o `natillera_db`) y el rol propietario.
3. Desactiva **Connection pooling** y copia la conexión **directa**. La usarás desde tu equipo para crear tablas y el administrador.
4. Activa **Connection pooling** y copia la conexión **pooled**. La usarás en Vercel; el servidor normalmente contiene `-pooler`.
5. Guarda ambas conexiones en un lugar privado. Verifica que apuntan a la **misma rama y base**.

Para este backend, usa el prefijo **`postgresql+psycopg2://`**. Si Neon muestra `postgresql://`, reemplaza solamente ese prefijo y conserva el resto, incluidos los parámetros SSL. La configuración de producción requiere `sslmode=require` o `sslmode=verify-full`; normalmente Neon ya lo incluye.

Ejemplos ficticios, **no los copies como credenciales reales**:

```text
Directa:
postgresql+psycopg2://ROL:CLAVE@ep-ejemplo.REGION.aws.neon.tech/neondb?sslmode=require

Pooled:
postgresql+psycopg2://ROL:CLAVE@ep-ejemplo-pooler.REGION.aws.neon.tech/neondb?sslmode=require
```

Copia únicamente la URL. No incluyas el comando `psql`, comillas externas del comando ni instrucciones como `export DATABASE_URL=`. Si Neon añade otros parámetros, consérvalos. Usa la URL que genera Neon para mantener correctamente codificados los caracteres especiales de la contraseña.

Referencia: [conexiones directas y pooled en Neon](https://neon.com/docs/connect/connection-pooling).

## 5. Crear las tablas y el administrador en Neon

**Este paso es obligatorio.** En producción el backend está configurado para no crear las tablas al arrancar. Una API desplegada con una base vacía no podrá iniciar sesión ni guardar información.

Los comandos de esta sección se ejecutan **en tu equipo**, desde `backend`. Aunque los ejecutes localmente, crearán las tablas en Neon porque les proporcionarás la conexión de Neon.

### 5.1. Crear un entorno Python propio

Desde la raíz del proyecto:

```bash
cd backend
```

Si el ZIP trajo una carpeta `.venv`, renómbrala a `venv.bak` desde el explorador; ese nombre está excluido por el `.gitignore` del proyecto. Los entornos virtuales se deben crear en cada equipo.

En **Windows, PowerShell**:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la activación por su política de scripts, no necesitas cambiar la política: en VS Code abre una terminal de tipo **Command Prompt / Símbolo del sistema**, entra a la carpeta `backend` de este proyecto y ejecuta:

```bat
.venv\Scripts\activate.bat
```

En **macOS/Linux**:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Normalmente verás `(.venv)` al inicio de la línea. A partir de ahora, con el entorno activado, ambos sistemas usan estos mismos comandos:

```bash
python --version
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Comprueba que `python --version` muestre `3.12...`. Si cierras la terminal, tendrás que volver a entrar en `backend` y activar el entorno antes de usar `python manage_db.py` o `python create_admin.py`.

### 5.2. Generar una clave de seguridad propia

Ejecuta:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Obtendrás una cadena aleatoria de 64 caracteres. Guárdala en privado: será tu `SECRET_KEY`. No es la contraseña del administrador ni la de Neon. No publiques capturas ni archivos que la contengan.

### 5.3. Crear `backend/.env`

En el explorador de VS Code, dentro de `backend`, crea un archivo llamado exactamente **`.env`**. Si ya existe uno entregado con el ZIP, reemplaza sus ajustes por los de tu propio despliegue. El archivo debe estar junto a `manage_db.py`; no dentro de `app` ni en la raíz.

Pega lo siguiente y sustituye los dos valores indicados:

```dotenv
ENVIRONMENT=production
DEBUG=False
AUTO_CREATE_TABLES=False
DATABASE_URL="REEMPLAZAR_POR_LA_CONEXION_DIRECTA_DE_NEON"
SECRET_KEY="REEMPLAZAR_POR_LA_CLAVE_ALEATORIA_GENERADA"
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
BACKEND_CORS_ORIGINS="https://example.com"
DB_POOL_SIZE=2
DB_MAX_OVERFLOW=0
```

- En `DATABASE_URL`, pega tu URL **directa**, ya con `postgresql+psycopg2://` y SSL.
- En `SECRET_KEY`, pega la clave que acabas de generar.
- `https://example.com` es un origen temporal válido para poder preparar la base sin conocer todavía tu dirección de Cloudflare. No es tu web final. Lo sustituirás en Vercel en el paso 8.
- Conserva `AUTO_CREATE_TABLES=False`: el comando de migración creará las tablas de manera explícita.
- Guarda el archivo. En Windows comprueba que no se llame `.env.txt`.

**No ejecutes `setup_local.py`, Docker ni `seed.py` para esta preparación en Neon.** `setup_local.py` configura otro recorrido, con PostgreSQL local. `seed.py` crea datos de demostración y está bloqueado para bases remotas. Aquí crearás una base limpia y un administrador con contraseña propia.

Los ajustes definidos en la terminal tienen prioridad sobre `.env`. Si habías configurado `DATABASE_URL` u otras variables para otro proyecto, usa una terminal sin esos ajustes para no conectarte a la base equivocada.

### 5.4. Crear las entidades con la herramienta incluida

En la terminal, **dentro de `backend` y con `.venv` activo**, ejecuta:

```bash
python manage_db.py check
```

Como la base es nueva, es normal obtener `"ok": false` con varias entradas `tabla_ausente:...`. Este comando solo revisa; todavía no crea nada. Si aparece un error de conexión, contraseña o configuración, resuélvelo antes de continuar.

Ahora crea el esquema:

```bash
python manage_db.py upgrade
```

Este comando lee los modelos de `backend/app/models/` y crea en Neon las tablas, columnas, claves primarias, claves foráneas, índices y restricciones definidos por el proyecto. También aplica los ajustes de compatibilidad incluidos en esta versión. No tienes que escribir los `CREATE TABLE` manualmente ni diseñar otra vez las relaciones.

Cuando termine correctamente, espera un resultado equivalente a:

```json
{"ok": true, "issues": {}}
```

Compruébalo con una segunda revisión:

```bash
python manage_db.py check
```

Debe volver a mostrar `"ok": true` y `"issues": {}`. Si no ocurre, no avances al despliegue: revisa el mensaje y la sección de errores de esta guía.

En esta versión, repetir `upgrade` permite completar la preparación sin borrar las tablas existentes. No es un sistema genérico que aplique cualquier cambio futuro de modelos: para futuras versiones sigue sus instrucciones de migración. Sobre una base que ya tenga información, prepara un respaldo recuperable antes de modificar su estructura.

### 5.5. Conocer las 11 tablas creadas

| Tabla | Qué almacena |
| --- | --- |
| `usuarios` | Cuentas de acceso, contraseña cifrada mediante hash y permisos. |
| `socios` | Identificación y datos de los integrantes de la natillera. |
| `finanzas_socio` | Movimientos financieros asociados a cada socio. |
| `prestamos` | Préstamos de los socios, saldos, cuotas e intereses. |
| `abonos_prestamo` | Pagos asociados a cada préstamo. |
| `actividades` | Actividades e información de sus ingresos y gastos. |
| `rifas` | Rifas y sus datos de boletas y resultados financieros. |
| `reuniones` | Reuniones y sus datos económicos. |
| `notas` | Notas y fechas programadas. |
| `historial_movimientos` | Registro de acciones de la aplicación para auditoría y reversión. |
| `login_limits` | Contadores para limitar intentos de inicio de sesión. |

Las relaciones con claves foráneas de esta versión son:

```text
socios.id ──► finanzas_socio.socio_id
socios.id ──► prestamos.socio_id
prestamos.id ──► abonos_prestamo.prestamo_id
```

Estas relaciones evitan, por ejemplo, que un abono apunte a un préstamo inexistente. No todas las tablas necesitan una clave foránea hacia otra: conserva el esquema que crea el código.

### 5.6. Verificar las tablas desde el panel de Neon

1. Regresa al proyecto en Neon.
2. Abre **SQL Editor**, que puede estar dentro de **Postgres database**.
3. Selecciona exactamente la misma **rama y base** de tu conexión directa.
4. Sustituye cualquier consulta de ejemplo del editor por la siguiente y pulsa **Run**:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;
```

Debes encontrar las 11 tablas de la lista anterior. Si añadiste tablas de ejemplo de Neon, podrían aparecer más; esas tablas adicionales no forman parte de Natillera.

Para inspeccionar las columnas:

```sql
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;
```

Para ver las relaciones creadas:

```sql
SELECT conrelid::regclass AS tabla,
       conname AS restriccion,
       pg_get_constraintdef(oid) AS definicion
FROM pg_constraint
WHERE contype = 'f'
  AND connamespace = 'public'::regnamespace
ORDER BY conrelid::regclass::text, conname;
```

Estas consultas solo leen información. También puedes explorar el esquema `public` desde **Tables** y actualizar la vista si estaba abierta antes de ejecutar `upgrade`.

Si no encuentras las tablas, compara rama, base y servidor del editor con los que elegiste en **Connect**. Crear tablas en una rama no prepara automáticamente todas las otras ramas que ya existían.

Referencia: [usar el editor SQL de Neon](https://neon.com/docs/get-started/query-with-neon-sql-editor).

### 5.7. Crear el primer administrador

De vuelta en tu terminal, dentro de `backend` y con el entorno activo:

```bash
python create_admin.py
```

El programa te pedirá:

1. **Usuario administrador:** escoge un nombre de entre 3 y 50 caracteres.
2. **Contraseña:** usa una contraseña propia de al menos 12 caracteres; el máximo es 72 bytes en UTF-8. Para evitar confusiones con ese límite, puedes usar letras, números y símbolos de un teclado convencional.
3. **Repetir contraseña:** escríbela nuevamente.

Al escribir la contraseña no se mostrarán letras ni asteriscos: es normal. Escribe y pulsa Enter. El programa debe mostrar **`Administrador creado`**.

Guarda el usuario y la contraseña en privado. La contraseña se almacena como hash en `usuarios`; no la insertes manualmente como texto en esa tabla. Tampoco uses las credenciales de demostración del README local.

En Neon puedes verificar que existe un administrador, sin consultar su hash:

```sql
SELECT id, username, is_admin, is_active
FROM public.usuarios;
```

Debes ver tu cuenta con `is_admin = true` e `is_active = true`. El programa se detiene si ya existe un administrador: en ese caso usa las credenciales que creaste, no borres la base para repetir este paso.

## 6. Desplegar el backend en Vercel

### 6.1. Importar tu repositorio

1. Entra a Vercel y selecciona **Add New → Project**.
2. Conecta tu GitHub si aún no está conectado. Autoriza el acceso al repositorio que creaste.
3. Busca `natillera-aprendiz` y pulsa **Import**.
4. Pon un nombre al proyecto, por ejemplo `natillera-api-aprendiz`.
5. En **Root Directory**, pulsa **Edit**, selecciona **`backend`** y confirma.
6. Verifica **Framework Preset: FastAPI**. El repositorio ya contiene `backend/vercel.json` y `backend/index.py` con esa configuración.
7. Deja los comandos de instalación y compilación en sus valores automáticos. No pongas `uvicorn`, `seed.py` ni `manage_db.py upgrade` como comando de build.

Vercel debe usar la versión indicada por `backend/.python-version`, que es Python 3.12. No selecciones Vite para este proyecto: esta publicación corresponde a la API.

Referencia: [desplegar FastAPI en Vercel](https://vercel.com/docs/frameworks/backend/fastapi).

### 6.2. Agregar las variables antes de desplegar

Abre **Environment Variables** en la pantalla de importación. Agrega cada nombre y valor en su campo, sin comillas externas. Si debes hacerlo después, entra a **Settings → Environment Variables** del proyecto.

Configura el entorno **Production** con estos valores:

| Nombre | Valor que debes poner |
| --- | --- |
| `ENVIRONMENT` | `production` |
| `DEBUG` | `False` |
| `AUTO_CREATE_TABLES` | `False` |
| `DATABASE_URL` | Tu conexión **pooled** de Neon, con `postgresql+psycopg2://` y SSL. |
| `SECRET_KEY` | La clave aleatoria que generaste; puedes usar la misma del `.env` privado de esta guía. |
| `ALGORITHM` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` |
| `BACKEND_CORS_ORIGINS` | Por ahora `https://example.com`; pondrás la URL real de Cloudflare en el paso 8. |
| `DB_POOL_SIZE` | `2` |
| `DB_MAX_OVERFLOW` | `0` |

No necesitas agregar `POSTGRES_USER`, `POSTGRES_PASSWORD` ni `POSTGRES_DB` de la plantilla local: la conexión remota ya lleva los datos necesarios. El prefijo de API predeterminado es `/api/v1`; mantenlo así.

La base y las tablas **ya deben existir** antes de publicar. Vercel no carga automáticamente tu archivo `.env` privado desde el equipo: debes guardar sus ajustes en el panel.

Para este primer recorrido trabaja con la rama GitHub **`main`** como rama de producción. No conectes despliegues de pruebas o **Preview** a esta misma base con datos reales. Cuando necesites previews, prepara una rama/base Neon separada, sus variables de Preview y los orígenes correspondientes.

Referencia: [administrar variables de entorno en Vercel](https://vercel.com/docs/environment-variables/managing-environment-variables).

### 6.3. Publicar y copiar la dirección estable

1. Pulsa **Deploy** y espera a que termine.
2. Si falla, abre los logs del despliegue; no continúes hasta corregir la causa.
3. En el proyecto, busca la dirección de **Production**, por ejemplo `https://natillera-api-aprendiz.vercel.app`.
4. Copia esa dirección estable. No uses una URL temporal que incluya el identificador de un despliegue.
5. Ábrela en el navegador. Debes ver un JSON parecido a:

```json
{
  "status": "online",
  "project": "Sistema de Gestión Natillera API",
  "docs": "/docs",
  "api_v1": "/api/v1"
}
```

Esto verifica que la API responde. **Todavía no demuestra la conexión a Neon**, porque la ruta raíz no consulta la base. La verificarás al iniciar sesión desde la web.

En producción `/docs` y `/openapi.json` están deshabilitados y pueden responder 404, aunque el JSON raíz mencione `/docs`. No necesitas habilitarlos para desplegar.

Si aparece una pantalla de acceso de Vercel en lugar del JSON, revisa **Settings → Deployment Protection** y asegúrate de que el dominio de producción de esta API permita acceso público según las opciones de tu plan. El navegador debe poder llamar a ese dominio; el inicio de sesión de Natillera protege las operaciones de la aplicación.

## 7. Publicar el frontend en Cloudflare Pages

### 7.1. Crear una aplicación Pages conectada a GitHub

1. Entra al panel de Cloudflare.
2. Busca **Workers & Pages** y pulsa **Create application**.
3. Elige **Pages** y la opción de importar o conectar un repositorio Git, normalmente **Connect to Git** o **Import an existing Git repository**. Si la pantalla abre primero Workers, busca la opción para cambiar a Pages.
4. Conecta GitHub y autoriza el acceso a tu repositorio.
5. Selecciona `natillera-aprendiz`.
6. Elige un nombre para el sitio, por ejemplo `natillera-web-aprendiz`.
7. Selecciona **`main`** como rama de producción.

Para este recorrido usa **Pages**. El archivo `frontend/wrangler.jsonc` también permite otra modalidad, Workers con Static Assets, pero no necesitas ejecutarlo ni configurar `wrangler deploy` al publicar por Pages.

Referencia: [conectar un repositorio Git a Pages](https://developers.cloudflare.com/pages/get-started/git-integration/).

### 7.2. Configurar la compilación

En los ajustes de build configura:

| Ajuste | Valor |
| --- | --- |
| Production branch | `main` |
| Root directory / Path | `frontend` |
| Framework preset | `React (Vite)` si aparece; si no, `None` y completa los campos manualmente. |
| Build command | `npm run build` |
| Build output directory | `dist` |

`dist` es relativo a la raíz seleccionada, `frontend`: no escribas `frontend/dist` si ya configuraste `frontend` como raíz. Cloudflare instalará las dependencias antes del build.

Agrega las siguientes variables de **compilación** para Production:

| Variable | Valor |
| --- | --- |
| `NODE_VERSION` | `24` |
| `VITE_API_URL` | `https://TU-BACKEND.vercel.app/api/v1` |

Sustituye `TU-BACKEND` por el dominio estable de Vercel que copiaste. La URL debe usar **HTTPS** y terminar exactamente en **`/api/v1`**, sin barra adicional al final. No pongas `localhost`, el dominio de Pages, `/docs`, comillas ni una contraseña.

Ejemplo: si tu API responde en `https://natillera-api-aprendiz.vercel.app/`, escribe `https://natillera-api-aprendiz.vercel.app/api/v1`.

**No agregues `DATABASE_URL`, `SECRET_KEY` ni contraseñas en Cloudflare ni en variables `VITE_*`.** Las variables `VITE_*` se incorporan al JavaScript que descarga el navegador y son públicas. La conexión de base de datos pertenece al backend.

Referencias: [React en Pages](https://developers.cloudflare.com/pages/framework-guides/deploy-a-react-site/), [versión de Node para los builds](https://developers.cloudflare.com/pages/configuration/build-image/).

### 7.3. Desplegar y guardar la URL

1. Pulsa **Save and Deploy**.
2. Espera a que finalice el build.
3. Abre la dirección estable de producción, por ejemplo `https://natillera-web-aprendiz.pages.dev`.
4. Debes ver el formulario de acceso de Natillera.
5. Copia el dominio estable del proyecto, sin el prefijo de un despliegue de preview.

El build ya incorpora `public/_redirects` para que se puedan recargar las rutas de React y genera las cabeceras de seguridad a partir del origen de tu API. No necesitas agregar funciones de Cloudflare para llamar a Vercel.

Es normal que el inicio de sesión aún no funcione si falta el siguiente paso: hasta ahora la API solo permite el origen temporal.

## 8. Autorizar la web en el backend: configurar CORS

**CORS** es la configuración con la que tu API le indica al navegador qué sitio puede llamarla. Como Pages y Vercel tienen dominios distintos, debes registrar la dirección real del frontend.

1. Regresa a tu proyecto de **Vercel**.
2. Abre **Settings → Environment Variables**.
3. Edita `BACKEND_CORS_ORIGINS` en **Production**.
4. Reemplaza `https://example.com` por la URL exacta de tu sitio de Cloudflare, por ejemplo:

```text
https://natillera-web-aprendiz.pages.dev
```

5. Guarda el cambio.
6. Abre **Deployments**, busca el despliegue de producción más reciente y elige **Redeploy**. Espera a que termine y confirma que sigue siendo la versión de producción.
7. En tu `backend/.env` privado puedes actualizar también ese origen para mantener anotada tu configuración; esto no sustituye el cambio en Vercel.

Reglas para el valor de CORS:

- Empieza por `https://`.
- No lleva `/` al final, `/login` ni `/api/v1`.
- No lleva asteriscos ni comillas en el panel.
- Si usas varios dominios reales, sepáralos por comas, por ejemplo `https://mi-sitio.pages.dev,https://mi-dominio.com`.

No basta con editar una variable y guardar: **Vercel aplica el nuevo valor a nuevos despliegues**. También en Cloudflare debes volver a compilar si cambias `VITE_API_URL`, porque su valor queda dentro del frontend publicado.

## 9. Verificar el recorrido completo

Ahora comprueba el funcionamiento desde tu URL de **producción** de Cloudflare:

1. Recarga la página.
2. Inicia sesión con el usuario y la contraseña que creaste mediante `create_admin.py`.
3. Confirma que abre el panel y que las pantallas pueden cargar sus datos. Una base nueva puede mostrar listas vacías y valores en cero.
4. En **Socios**, registra un socio ficticio con datos de prueba, sin información personal real.
5. Recarga la página y confirma que el socio sigue apareciendo.
6. En Neon, selecciona la misma rama/base y verifica:

```sql
SELECT id, nombre
FROM public.socios
ORDER BY id DESC
LIMIT 5;
```

7. Comprueba que aparece el socio de prueba.
8. Abre una sección interna de la web y recarga para verificar que no aparece un error 404.
9. Cierra sesión y vuelve a entrar.

Estas comprobaciones validan **Pages → Vercel → Neon**, incluida la lectura y escritura de datos. Mantén los datos de prueba claramente identificados mientras aprendes.

### Lista de comprobación

- [ ] Mi repositorio GitHub contiene `backend` y `frontend` en la raíz.
- [ ] No publiqué `.env`, claves, conexiones ni bases de datos.
- [ ] Elegí una rama y una base concretas en Neon.
- [ ] Ejecuté `python manage_db.py upgrade` sobre esa base.
- [ ] `python manage_db.py check` devuelve `"ok": true`.
- [ ] Puedo ver las 11 tablas en Neon.
- [ ] Creé el administrador con una contraseña propia.
- [ ] Vercel usa `backend` como raíz y la conexión pooled correcta.
- [ ] El dominio de producción de la API responde con `"status": "online"`.
- [ ] Cloudflare Pages usa `frontend`, `npm run build`, `dist` y Node 24.
- [ ] `VITE_API_URL` termina exactamente en `/api/v1` y apunta a Vercel.
- [ ] CORS tiene la URL real de Pages y volví a desplegar el backend.
- [ ] Puedo iniciar sesión, crear un socio de prueba y verlo en Neon.
- [ ] Puedo recargar una ruta interna del frontend.

## 10. Resolver errores frecuentes

El formulario de acceso puede mostrar un mensaje genérico incluso si el problema es la conexión. Para ver la causa, abre las herramientas del navegador con **F12** o **Inspeccionar**, entra a **Network / Red** y repite el intento. Revisa la URL y el estado de la petición a la API. En Vercel consulta también los **Logs** de ejecución, no solo los del build. No compartas tokens, cabeceras `Authorization`, contraseñas ni conexiones al pedir ayuda.

| Síntoma | Qué revisar y cómo resolverlo |
| --- | --- |
| `python`, `py`, `git` o `npm` no se reconoce | Instala la herramienta, verifica su `PATH` y abre otra terminal o reinicia VS Code. |
| PowerShell bloquea `Activate.ps1` | Abre Command Prompt en VS Code, entra a `backend` y usa `.venv\Scripts\activate.bat`. |
| `No such file`, `can't open file manage_db.py` o falta `requirements.txt` | Estás en otra carpeta. Los comandos Python de preparación se ejecutan desde `backend`. |
| `ModuleNotFoundError` | Activa tu `.venv` y ejecuta `python -m pip install -r requirements.txt` dentro de `backend`. |
| `DATABASE_URL: Field required` o error de `SECRET_KEY` | Revisa que exista `backend/.env`, su nombre no termine en `.txt`, esté guardado y tenga los valores reales. En Vercel revisa las variables de Production y vuelve a desplegar. |
| `NoSuchModuleError` o falta un driver PostgreSQL | Usa `postgresql+psycopg2://` e instala `requirements.txt`; no selecciones otro driver al copiar la conexión. |
| Error de SSL en producción | Conserva los parámetros de Neon y verifica `sslmode=require` o `sslmode=verify-full`. |
| `password authentication failed`, no encuentra servidor o agota el tiempo | Vuelve a copiar la URL desde Connect, verifica rol, contraseña, base, acceso a Internet y que el compute pueda activarse. Una red institucional puede bloquear conexiones PostgreSQL. |
| `tabla_ausente` al ejecutar el primer `check` | Es esperado en una base nueva. Ejecuta `upgrade` y luego `check` nuevamente. |
| `relation ... does not exist` al iniciar sesión | Faltan tablas en la base utilizada por Vercel. Compara su URL pooled con la directa del `.env`: ambas deben seleccionar la misma rama y base. Ejecuta `upgrade` con la conexión directa correcta. |
| `upgrade` cancela por integridad inválida o bloqueo | No borres datos ni desactives restricciones. En una base existente prepara respaldo, revisa los errores y pide apoyo al instructor; para bloqueos, programa la migración sin escrituras concurrentes. |
| `Ya existe un administrador` | La cuenta ya se creó. Usa esas credenciales; no ejecutes un semillero ni elimines usuarios para evitar el mensaje. |
| Vercel responde 404 en `/` | Revisa Root Directory `backend`, Framework FastAPI y que `index.py` y `vercel.json` estén publicados. |
| Vercel muestra 500 o `FUNCTION_INVOCATION_FAILED` | Abre los logs de ejecución y revisa primero la configuración, las dependencias y Neon. Un build exitoso no garantiza que la función arranque. |
| La API devuelve HTML de acceso de Vercel, 401 o 403 antes de llegar a Natillera | Revisa Deployment Protection y usa el dominio público de producción de la API. |
| `/docs` responde 404 | Es esperado en producción para esta aplicación. Prueba `/` y el acceso desde el frontend. |
| Cloudflare no encuentra `package.json` | Configura Root directory `frontend` y confirma que esa carpeta está en la raíz de GitHub. |
| Cloudflare no encuentra `dist` | Con raíz `frontend`, el output es `dist`. Revisa antes si `npm run build` falló. |
| El build dice `Configura VITE_API_URL=...` | Agrega la variable de build en Cloudflare Production con HTTPS y `/api/v1`, sin barra final, y vuelve a desplegar. |
| El build falla por versión de Node | Configura `NODE_VERSION=24`, conserva `.node-version` y vuelve a ejecutar el build. |
| Error CORS, `Failed to fetch` o petición bloqueada | Revisa el dominio exacto del navegador, `BACKEND_CORS_ORIGINS`, el redeploy de Vercel y que `VITE_API_URL` apunte al backend correcto. La política de seguridad del frontend también usa esa URL al compilar. |
| La web todavía llama a una URL anterior | Cambia `VITE_API_URL` en Cloudflare y genera un nuevo despliegue de producción. Editar el `.env` de tu equipo no cambia una web ya publicada. |
| Login devuelve 401 desde la API de Natillera | Verifica usuario y contraseña, y que el administrador se haya creado en la misma base que usa Vercel. |
| Login devuelve 429 | Se alcanzó el límite de intentos. Espera al siguiente intervalo de un minuto antes de volver a intentar y confirma las credenciales. |
| Funciona en `pages.dev` pero falla en una URL de preview o dominio propio | Son orígenes diferentes. Para un dominio propio autorizado, agrégalo a CORS y redespliega; configura previews con su base separada antes de usarlos. |
| Git rechaza el primer push por historial distinto | Comprueba que creaste un repositorio vacío. No uses `push --force` como solución automática; para este recorrido resulta más sencillo crear otro repositorio vacío y cambiar `origin`. |

Si necesitas pedir ayuda, indica el paso, el comando y el mensaje de error **ocultando todos los secretos**. No envíes tu `.env` ni una captura completa del panel de conexiones.

## 11. Publicar cambios después del primer despliegue

Para cambios de código, abre una terminal en la **raíz del proyecto**, revisa y sube la nueva versión:

```bash
git status
git add .
git diff --cached --stat
git commit -m "Describir el cambio realizado"
git push
```

Revisa los archivos antes del commit para no publicar secretos. Vercel y Cloudflare, al estar conectados a `main`, podrán generar nuevos despliegues. Comprueba su estado en ambos paneles y prueba de nuevo el inicio de sesión.

Cambiar código y cambiar una variable son procesos distintos:

| Qué cambiaste | Qué debes hacer |
| --- | --- |
| Código del frontend | Subir el cambio y comprobar el nuevo build de Cloudflare. |
| Código del backend | Subir el cambio y comprobar el nuevo despliegue de Vercel. |
| `VITE_API_URL` | Guardarla en Cloudflare y recompilar el frontend. |
| CORS o una variable del backend | Guardarla en Vercel y redesplegar el backend. |
| Estructura de base de datos | Revisar la migración de esa versión, probarla en otra rama/base, preparar respaldo y aplicarla con conexión directa antes de publicar el código que la necesita. |

No elimines tablas ni vuelvas a crear la base cuando quieras actualizar la aplicación: eso perdería información. El ZIP y el repositorio contienen el código; **no son un respaldo de los datos guardados en Neon**.

Si una versión nueva del código falla, las plataformas permiten volver a un despliegue anterior. Eso no revierte cambios hechos a los datos o al esquema de Neon. Conserva un respaldo recuperable antes de cualquier cambio de base de datos y solicita acompañamiento antes de restaurarlo.

## 12. Datos que debes conservar en privado

Guarda estos valores en un gestor de contraseñas o una nota privada, **fuera del repositorio**:

- URL de tu repositorio GitHub.
- Proyecto, región, rama, base y rol de Neon.
- Conexión directa y conexión pooled de esa misma base.
- Nombre del proyecto Vercel y URL estable de producción de la API.
- Nombre del proyecto Cloudflare Pages y URL estable de producción del frontend.
- `SECRET_KEY` del backend.
- Usuario y contraseña del administrador de Natillera.

No completes esta lista con contraseñas dentro de `aprendiz.md`: este documento se puede compartir y subir a GitHub.
