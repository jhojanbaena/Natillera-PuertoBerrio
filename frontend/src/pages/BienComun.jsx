import React, { useEffect, useState } from "react";
import { HandHeart, ChevronDown } from "lucide-react";
import api from "../api/client";
import { formatMoney } from "../utils/formatters";

const ESTADO_PRESTAMO = {
  PAGADO: { texto: "Pagado", clase: "bg-emerald-50 text-emerald-700" },
  EN_MORA: { texto: "En mora", clase: "bg-rose-50 text-rose-700" },
  PENDIENTE: { texto: "Al día", clase: "bg-amber-50 text-amber-700" },
};

export const BienComun = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [verDetalle, setVerDetalle] = useState(false);

  useEffect(() => {
    api.get("/finanzas/bien-comun")
      .then((res) => setData(res.data))
      .catch((err) => console.error("Error al cargar Bien Común", err))
      .finally(() => setLoading(false));
  }, []);

  // Intereses del bien común efectivamente cobrados (los que suman al dinero total).
  const interesesCobrados = data?.total_intereses_bien_comun ?? data?.total_intereses_obtenidos;
  const prestamos = data?.intereses_por_prestamo || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl md:text-3xl font-black text-slate-800 tracking-tight flex items-center gap-2.5">
          <HandHeart className="w-7 h-7 text-emerald-600" />
          Bien Común
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">Multas administradas como recurso común, fuera de la liquidación individual.</p>
      </div>

      {loading ? (
        <div className="py-16 text-center text-slate-400 text-sm">Cargando resumen de Bien Común...</div>
      ) : data && (
        <div className="space-y-4">
          <div className="bg-slate-800 rounded-2xl p-5 shadow-sm text-white">
            <p className="text-xs font-bold text-slate-300 uppercase tracking-wider">Dinero total</p>
            <p className="text-2xl font-black mt-1">{formatMoney(data.total_dinero_total ?? data.total_multas_recaudadas)}</p>
            <p className="text-xs text-slate-300 mt-2">Incluye multas pagadas e intereses del bien común ya cobrados</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-emerald-50 rounded-2xl p-5 border border-emerald-200/80 shadow-sm">
              <p className="text-xs font-bold text-emerald-700 uppercase tracking-wider">Multas recaudadas</p>
              <p className="text-2xl font-black text-emerald-700 mt-1">{formatMoney(data.total_multas_recaudadas)}</p>
            </div>
            <div className="bg-amber-50 rounded-2xl p-5 border border-amber-200/80 shadow-sm">
              <p className="text-xs font-bold text-amber-700 uppercase tracking-wider">Intereses cobrados</p>
              <p className="text-2xl font-black text-amber-700 mt-1">{formatMoney(interesesCobrados)}</p>
              <p className="text-[11px] text-amber-700/80 mt-1">
                Parte del bien común de los intereses ya pagados.
                {data.total_intereses_bien_comun != null && (
                  <> Total de intereses cobrados en préstamos: {formatMoney(data.total_intereses_obtenidos)} (incluye la parte de cada socio).</>
                )}
              </p>
            </div>
            <div className="bg-white rounded-2xl p-5 border border-dashed border-slate-300 shadow-sm">
              <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">Intereses pendientes</p>
              <p className="text-2xl font-black text-slate-700 mt-1">{formatMoney(data.total_intereses_pendientes_bien_comun)}</p>
              <p className="text-[11px] text-slate-500 mt-1">
                Parte del bien común de cuotas vencidas sin pagar. Aún no se recibe: no suma al dinero total.
                {" "}Total pendiente en préstamos: {formatMoney(data.total_intereses_pendientes)}.
              </p>
            </div>
          </div>

          {prestamos.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
              <button
                type="button"
                onClick={() => setVerDetalle((v) => !v)}
                aria-expanded={verDetalle}
                className="w-full flex items-center justify-between gap-3 px-5 py-4 border-b border-slate-100 text-left hover:bg-slate-50/70"
              >
                <div>
                  <h2 className="font-bold text-slate-800">Intereses por préstamo</h2>
                  <p className="text-[11px] text-slate-400">Cobrados y pendientes de cada préstamo; se actualiza con cada abono registrado.</p>
                </div>
                <ChevronDown className={`w-5 h-5 text-slate-400 transition-transform ${verDetalle ? "rotate-180" : ""}`} />
              </button>
              {verDetalle && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-[11px] uppercase tracking-wider text-slate-400 border-b border-slate-100">
                        <th className="px-5 py-2">Préstamo</th>
                        <th className="px-3 py-2 text-right">Cobrado</th>
                        <th className="px-3 py-2 text-right">Cobrado bien común</th>
                        <th className="px-3 py-2 text-right">Pendiente</th>
                        <th className="px-5 py-2 text-right">Pendiente bien común</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {prestamos.map((p) => {
                        const estado = ESTADO_PRESTAMO[p.estado] || { texto: p.estado, clase: "bg-slate-100 text-slate-600" };
                        return (
                          <tr key={p.prestamo_id} className="text-slate-700">
                            <td className="px-5 py-2.5">
                              <p className="font-bold text-slate-800">{p.socio_nombre}</p>
                              <p className="text-[11px] text-slate-400">
                                Préstamo #{p.prestamo_id}{" "}
                                <span className={`ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold ${estado.clase}`}>{estado.texto}</span>
                              </p>
                            </td>
                            <td className="px-3 py-2.5 text-right">{formatMoney(p.intereses_cobrados)}</td>
                            <td className="px-3 py-2.5 text-right font-bold text-amber-700">{formatMoney(p.intereses_cobrados_bien_comun)}</td>
                            <td className="px-3 py-2.5 text-right text-slate-500">{formatMoney(p.intereses_pendientes)}</td>
                            <td className="px-5 py-2.5 text-right text-slate-500">{formatMoney(p.intereses_pendientes_bien_comun)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-100">
              <h2 className="font-bold text-slate-800">Socios registrados</h2>
            </div>
            <div className="divide-y divide-slate-100">
              {data.socios.map((socio) => (
                <div key={socio.id} className="flex items-center justify-between px-5 py-3 text-sm">
                  <p className="font-bold text-slate-800">{socio.nombre}</p>
                  <p className="font-black text-emerald-700">{formatMoney(socio.participacion)}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
