import axios from "axios";
import { getAnioConsulta, setAnioConsulta } from "../utils/periodo";

const API_BASE_URL = import.meta.env.VITE_API_URL || "/api/v1";

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Interceptor para inyectar token JWT automáticamente
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // Año que se está consultando (solo cuando no es el activo).
    const anio = getAnioConsulta();
    if (anio) {
      config.headers["X-Periodo"] = anio;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Interceptor para manejar expiración de token o 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    // El año guardado ya no existe: volver al año activo.
    const detalle = error.response?.data?.detail;
    if (
      error.response?.status === 404 &&
      getAnioConsulta() &&
      typeof detalle === "string" &&
      /^El año d+ no existe$/.test(detalle)
    ) {
      setAnioConsulta(null);
      window.location.reload();
    }
    return Promise.reject(error);
  }
);

export default api;
