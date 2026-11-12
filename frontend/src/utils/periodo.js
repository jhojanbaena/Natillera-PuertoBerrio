// Año (periodo) con el que trabaja la aplicación.
// - Sin año guardado: se trabaja con el año activo.
// - Con año guardado: se consulta ese año (solo lectura); el cliente HTTP lo envía
//   en la cabecera X-Periodo y el backend responde con los datos de ese año.
const CLAVE = "anio_consulta";

export const getAnioConsulta = () => {
  try {
    return localStorage.getItem(CLAVE);
  } catch {
    return null;
  }
};

export const setAnioConsulta = (anio) => {
  try {
    if (anio) localStorage.setItem(CLAVE, String(anio));
    else localStorage.removeItem(CLAVE);
  } catch {
    // Sin almacenamiento disponible: se sigue en el año activo.
  }
};

// Año de los datos en pantalla (lo fija PeriodoProvider al cargar).
let anioTrabajo = null;
export const setAnioTrabajo = (anio) => {
  anioTrabajo = anio;
};
export const anioDeTrabajo = () => anioTrabajo ?? new Date().getFullYear();
