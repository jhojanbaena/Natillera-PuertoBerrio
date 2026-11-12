import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import api from "../api/client";
import { useAuth } from "./AuthContext";
import { setAnioConsulta, setAnioTrabajo } from "../utils/periodo";

const PeriodoContext = createContext(null);

export const PeriodoProvider = ({ children }) => {
  const { token } = useAuth();
  const [periodo, setPeriodo] = useState(null);

  const cargar = useCallback(async () => {
    try {
      const res = await api.get("/periodos/actual");
      setAnioTrabajo(res.data.anio_consultado);
      setPeriodo(res.data);
    } catch (err) {
      console.error("No se pudo cargar el año activo", err);
      // Sin información del año se sigue en el activo (el backend decide).
      setPeriodo({ anio_activo: null, anio_consultado: null, solo_lectura: false });
    }
  }, []);

  useEffect(() => {
    if (token) cargar();
    else setPeriodo(null);
  }, [token, cargar]);

  // Cambia el año en pantalla y recarga la aplicación para que todo se lea de ese año.
  const cambiarAnio = useCallback((anio) => {
    setAnioConsulta(periodo && anio === periodo.anio_activo ? null : anio);
    window.location.assign("/");
  }, [periodo]);

  const volverAlActivo = useCallback(() => {
    setAnioConsulta(null);
    window.location.assign("/");
  }, []);

  return (
    <PeriodoContext.Provider value={{ periodo, listo: !token || periodo !== null, cambiarAnio, volverAlActivo, recargar: cargar }}>
      {children}
    </PeriodoContext.Provider>
  );
};

export const usePeriodo = () => {
  const context = useContext(PeriodoContext);
  if (!context) {
    throw new Error("usePeriodo debe usarse dentro de un PeriodoProvider");
  }
  return context;
};
