import React, { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

const STORAGE_KEY = "natillera-tema";

const temaInicial = () => {
  try {
    const guardado = localStorage.getItem(STORAGE_KEY);
    if (guardado === "dark" || guardado === "light") return guardado;
  } catch {
    /* sin acceso a localStorage */
  }
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
};

export const ThemeToggle = ({ className = "" }) => {
  const [tema, setTema] = useState(temaInicial);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", tema === "dark");
    try {
      localStorage.setItem(STORAGE_KEY, tema);
    } catch {
      /* sin acceso a localStorage */
    }
  }, [tema]);

  const oscuro = tema === "dark";
  return (
    <button
      type="button"
      onClick={() => setTema(oscuro ? "light" : "dark")}
      title={oscuro ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
      aria-label={oscuro ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
      className={`p-2 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-100 transition-colors ${className}`}
    >
      {oscuro ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
    </button>
  );
};
