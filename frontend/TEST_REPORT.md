# Pruebas del frontend y login

Fecha: 20 de octubre de 2026. Frontend: http://localhost:5173;
API: http://localhost:8001/api/v1; persistencia: PostgreSQL Docker local.

## Resultado del login en navegador

| Caso | Resultado |
| --- | --- |
| Abrir la aplicación sin sesión | Redirección a `/login` |
| Enviar formulario vacío | Validación nativa «Completa este campo» |
| `admin` con contraseña incorrecta | Mensaje «Nombre de usuario o contraseña incorrectos»; permanece en login |
| `admin / 12345678` | Acceso al dashboard y perfil Administrador General |
| Recargar con sesión | Conserva acceso al dashboard |
| Cerrar sesión | Vuelve a login |
| Abrir `/socios` tras cerrar sesión | Vuelve a login |
| Iniciar sesión nuevamente | Vuelve al dashboard correctamente |

Se observó «Servidor Conectado», cinco socios y métricas financieras del semillero.
Se abrieron socios, préstamos, eventos, liquidación, historial y bien común.
Préstamos mostró dos créditos y su saldo; eventos mostró dos actividades;
liquidación mostró cinco socios; historial mostró su estado vacío; bien común
mostró los cinco socios y su participación. Son comprobaciones de carga, no
validación completa de sus operaciones o cálculos.

## Comprobaciones técnicas

- `npm ci`: instalación correcta, sin modificar el código funcional.
- `npm run build`: correcto, salida en `dist`.
- `npm run lint`: código 0, con 24 advertencias existentes (imports sin usar,
  efectos de React, Fast Refresh y referencia a `logout`).
- Consola del navegador: un AxiosError HTTP 401 correspondiente a la contraseña
  incorrecta probada; no se observaron otros errores en el flujo hasta la segunda
  entrada al dashboard.
- La instalación informó 10 vulnerabilidades (2 moderadas, 8 altas). No se
  investigaron individualmente ni se ejecutó `npm audit fix`.

El servidor Vite se inició con `VITE_API_URL=http://localhost:8001/api/v1`:
el proxy predeterminado del proyecto apunta a 8000. No se cambió la URL de
producción ni la configuración del proxy.

## Alcance pendiente

No se probaron exhaustivamente CRUD, cuentas lectoras/inactivas desde la UI,
expiración de sesión, fallos de red, dispositivos móviles ni accesibilidad.
La lectura del formulario muestra labels sin asociación `htmlFor`/`id`; conviene
corregirlo para que los campos tengan nombres accesibles.
Actualización del 21 de octubre de 2026: los seis defectos de negocio del backend
se corrigieron y validaron con pruebas API en PostgreSQL. Esta revisión de interfaz
corresponde al 20 de octubre; no constituye una repetición de todos los flujos UI.

Las pruebas de interfaz se ejecutaron manualmente mediante automatización del
navegador; no se añadió una suite E2E al repositorio.
