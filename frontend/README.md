# Frontend de Natillera

React, Vite, Tailwind y Axios. Requiere el backend y PostgreSQL descritos en el README de la raíz.

## Ejecutar con el backend local en 8001

Desde `frontend`, en macOS/Linux:

```bash
npm ci
VITE_API_URL=http://localhost:8001/api/v1 npm run dev -- --host 127.0.0.1
```

Abre http://localhost:5173. En PowerShell, configura primero
`$env:VITE_API_URL="http://localhost:8001/api/v1"` y luego ejecuta `npm run dev`.
También puedes crear `frontend/.env.local` con `VITE_API_URL=http://localhost:8001/api/v1`.
Reinicia Vite cuando cambies esta variable.

Si omites `VITE_API_URL`, el proxy de Vite apunta al backend en el puerto 8000.
Para producción, establece la URL pública de la API antes de compilar.

## Login de demostración

Después de ejecutar el semillero en la BD local: usuario `admin`, contraseña `12345678`.

1. Con campos vacíos, el formulario debe solicitar completarlos.
2. Con contraseña incorrecta, debe mostrar el mensaje del backend sin entrar.
3. Con credenciales válidas, debe abrir el dashboard y mostrar Administrador General.
4. Al recargar, debe conservar la sesión.
5. Al cerrar sesión, debe volver a `/login`.
6. Al abrir `/socios` sin sesión, debe redirigir a `/login`.

Estos seis casos se validaron en el navegador el 20 de octubre de 2026 con la
API real en 8001 y PostgreSQL Docker. Se comprobó además la carga de las siete
vistas autenticadas. Esto no equivale a probar todas las operaciones CRUD.

## Verificación técnica

```bash
VITE_API_URL=https://TU-BACKEND.vercel.app/api/v1 npm run build
npm run lint
```

La configuración vigente de Cloudflare Pages/Workers y las variables están en el [README general](../README.md). La compilación requiere una URL HTTPS completa terminada en `/api/v1` y genera la CSP para ese origen. `_redirects` habilita las rutas SPA; `_headers` añade las cabeceras de seguridad.

La compilación se verifica con la versión actualizada de Vite. El lint conserva advertencias existentes. `npm audit --omit=dev` no detectó vulnerabilidades; `npm audit` completo conserva alertas de desarrollo de Tailwind 3. Consulta [SECURITY_REVIEW.md](../SECURITY_REVIEW.md) para resultados actuales. [TEST_REPORT.md](TEST_REPORT.md) conserva la revisión histórica del navegador.
