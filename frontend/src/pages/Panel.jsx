import React, { useEffect, useState } from "react";
import { SquareTerminal, AlertTriangle } from "lucide-react";
import api from "../api/client";

// Panel del Desarrollador: exclusivo de ese rol. Por ahora está vacío;
// aquí se irán agregando sus funcionalidades.
export const Panel = () => {
  const [estado, setEstado] = useState("cargando");

  useEffect(() => {
    api.get("/panel")
      .then(() => setEstado("listo"))
      .catch(() => setEstado("error"));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl md:text-3xl font-black text-slate-800 tracking-tight flex items-center gap-2.5">
          <SquareTerminal className="w-7 h-7 text-purple-600" />
          Panel
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">Apartado exclusivo del rol Desarrollador.</p>
      </div>

      {estado === "error" ? (
        <div className="p-6 bg-rose-50 border border-rose-200 rounded-2xl text-rose-700 text-sm">
          <p className="font-bold flex items-center gap-2"><AlertTriangle className="w-5 h-5" /> No se pudo verificar el acceso al Panel.</p>
        </div>
      ) : (
        <section className="bg-white rounded-2xl border border-dashed border-slate-300 p-10 text-center">
          <SquareTerminal className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <p className="font-bold text-slate-700">Aún no hay funcionalidades en el Panel</p>
          <p className="text-sm text-slate-500 mt-1">Se irán agregando progresivamente.</p>
        </section>
      )}
    </div>
  );
};
