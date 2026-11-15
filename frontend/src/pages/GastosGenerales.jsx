import React, { useCallback, useEffect, useState } from "react";
import { Receipt, Users, Calculator, AlertTriangle } from "lucide-react";
import api from "../api/client";
import { useAuth } from "../context/AuthContext";
import { LineasEditables } from "../components/LineasEditables";
import { formatMoney } from "../utils/formatters";
import { anioDeTrabajo } from "../utils/periodo";

// Gastos generales del año: se dividen en partes iguales entre los socios activos y
// ese valor se descuenta automáticamente de la liquidación final de cada uno.
export const GastosGenerales = () => {
  const { user } = useAuth();
  const isAdmin = !!user?.is_admin;
  const [anio, setAnio] = useState(() => anioDeTrabajo());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pendientes, setPendientes] = useState(0);

  const cargar = useCallback(async (anioConsulta) => {
    try {
      setError("");
      const res = await api.get("/gastos-generales", { params: { anio: anioConsulta } });
      setData(res.data);
    } catch (err) {
      console.error(err);
      setError("No se pudieron cargar los gastos generales.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    cargar(anio);
  }, [anio, cargar]);

  const cambiarAnio = (nuevo) => {
    if (pendientes > 0 && !window.confirm("Hay líneas sin guardar. ¿Cambiar de año y descartarlas?")) return;
    setData(null);
    setAnio(nuevo);
  };

  const anios = data?.anios_disponibles?.length ? data.anios_disponibles : [anio];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-black text-slate-800 tracking-tight flex items-center gap-2.5">
            <Receipt className="w-7 h-7 text-purple-600" />
            Gastos Generales
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Gastos de la natillera repartidos en partes iguales entre los socios activos y descontados de su liquidación.
          </p>
        </div>
        <div>
          <label className="sr-only" htmlFor="anio-gastos">Año de liquidación</label>
          <select
            id="anio-gastos"
            value={anio}
            onChange={(e) => cambiarAnio(Number(e.target.value))}
            className="px-3 py-2 bg-white border border-slate-200 rounded-xl text-sm font-bold text-slate-700 outline-none focus:border-purple-400 focus:ring-2 focus:ring-purple-100"
          >
            {anios.map((a) => <option key={a} value={a}>Liquidación {a}</option>)}
          </select>
        </div>
      </div>

      {loading && !data ? (
        <div className="py-16 text-center text-slate-400 text-sm">
          <div className="w-6 h-6 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
          Cargando gastos generales...
        </div>
      ) : error ? (
        <div className="p-6 bg-rose-50 border border-rose-200 rounded-2xl text-rose-700 text-sm">
          <p className="font-bold flex items-center gap-2"><AlertTriangle className="w-5 h-5" /> {error}</p>
          <button onClick={() => cargar(anio)} className="mt-3 px-4 py-2 bg-rose-600 text-white rounded-xl text-xs font-bold">Reintentar</button>
        </div>
      ) : data && (
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-6 items-start">
          {/* Resumen automático (arriba en móvil, a la derecha en escritorio) */}
          <aside className="lg:order-2 lg:sticky lg:top-24 bg-gradient-to-br from-purple-700 to-fuchsia-600 rounded-2xl p-5 text-white shadow-md shadow-purple-600/20 space-y-4">
            <div>
              <p className="text-xs font-bold text-purple-100 uppercase tracking-wider">Total de gastos {data.anio}</p>
              <p className="text-3xl font-black mt-1">{formatMoney(data.total_gastos)}</p>
            </div>
            <div className="flex items-center justify-between border-t border-white/20 pt-3">
              <p className="text-sm text-purple-100 flex items-center gap-2"><Users className="w-4 h-4" /> Socios activos</p>
              <p className="text-xl font-black">{data.socios_activos}</p>
            </div>
            <div className="bg-white/15 rounded-xl p-3">
              <p className="text-xs font-bold text-purple-100 uppercase tracking-wider flex items-center gap-1.5">
                <Calculator className="w-3.5 h-3.5" /> Descuento por socio
              </p>
              <p className="text-2xl font-black mt-0.5">{formatMoney(data.gasto_por_socio)}</p>
              <p className="text-[11px] text-purple-100 mt-1">
                {data.socios_activos > 0
                  ? `${formatMoney(data.total_gastos)} ÷ ${data.socios_activos} socio${data.socios_activos === 1 ? "" : "s"} activo${data.socios_activos === 1 ? "" : "s"}`
                  : "No hay socios activos: no se reparte ningún valor."}
              </p>
            </div>
            <p className="text-[11px] text-purple-100">
              Se descuenta automáticamente de la liquidación final {data.anio} de cada socio activo (aparece como "Gastos Generales" en el desglose).
            </p>
          </aside>

          {/* Líneas de gastos */}
          <section className="lg:order-1 bg-white rounded-2xl border border-slate-200/80 shadow-sm p-4 sm:p-5">
            <h2 className="font-bold text-slate-800 mb-3">Conceptos de gasto ({data.gastos.length})</h2>
            <LineasEditables
              items={data.gastos}
              campoNombre="descripcion"
              campoValor="monto"
              etiquetaNombre="Nombre o descripción del gasto"
              etiquetaValor="Valor"
              placeholderNombre="Ej. Papelería, transporte, materiales..."
              textoBoton="AGREGAR NUEVO GASTO"
              vacio={`No hay gastos registrados para ${data.anio}. El descuento por socio es $0.`}
              editable={isAdmin}
              onPendientesChange={setPendientes}
              onCrear={async (descripcion, monto) => {
                await api.post("/gastos-generales", { descripcion, monto, anio: data.anio });
                await cargar(data.anio);
              }}
              onGuardar={async (id, descripcion, monto) => {
                await api.put(`/gastos-generales/${id}`, { descripcion, monto });
                await cargar(data.anio);
              }}
              onEliminar={async (id) => {
                await api.delete(`/gastos-generales/${id}`);
                await cargar(data.anio);
              }}
            />
            {!isAdmin && <p className="mt-3 text-[11px] text-slate-400">Solo un administrador puede modificar los gastos.</p>}
          </section>
        </div>
      )}
    </div>
  );
};
