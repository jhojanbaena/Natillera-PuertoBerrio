import axios from "axios";

// Cliente del portal de socios: token propio, separado del de administración.
// No envía la cabecera X-Periodo: el socio solo ve el año activo.
const API_BASE_URL = import.meta.env.VITE_API_URL || "/api/v1";
export const SOCIO_TOKEN = "socio_token";
const AVISO = "socio_aviso";

export const leerTokenSocio = () => {
  try {
    return localStorage.getItem(SOCIO_TOKEN);
  } catch {
    return null;
  }
};

export const guardarTokenSocio = (token) => localStorage.setItem(SOCIO_TOKEN, token);

export const cerrarSesionSocio = (aviso) => {
  try {
    localStorage.removeItem(SOCIO_TOKEN);
    if (aviso) sessionStorage.setItem(AVISO, aviso);
  } catch {
    // Almacenamiento bloqueado: el token tampoco pudo guardarse.
  }
};

// Mensaje que se muestra en el login después de que la sesión terminó.
export const leerAvisoSocio = () => {
  try {
    return sessionStorage.getItem(AVISO);
  } catch {
    return null;
  }
};

export const limpiarAvisoSocio = () => {
  try {
    sessionStorage.removeItem(AVISO);
  } catch {
    // Sin almacenamiento disponible: no hay aviso que limpiar.
  }
};

const socioApi = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

socioApi.interceptors.request.use((config) => {
  const token = leerTokenSocio();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const ingresarSocio = async (cedula, clave) => {
  const { data } = await socioApi.post("/portal-socio/login", { username: cedula, password: clave });
  guardarTokenSocio(data.access_token);
};

export const obtenerMiHoja = async () => (await socioApi.get("/portal-socio/mi-hoja")).data;
