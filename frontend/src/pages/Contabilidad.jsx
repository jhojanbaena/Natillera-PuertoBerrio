import React, { useCallback, useEffect, useState } from "react";
import {
  Scale, Landmark, Save, History, CheckCircle2, AlertTriangle, TrendingUp, ChevronDown, ChevronUp, Info,
} from "lucide-react";
import api from "../api/client";
import { useAuth } from "../context/AuthContext";
import { LineasEditables } from "../components/LineasEditables";
import { formatMoney } from "../utils/formatters";

const num = (v) => Number(v || 0);

const ESTADOS = {
  CUADRADA: {
    titulo: "CONTABILIDAD CUADRADA",
    caja: "bg-emerald-50 border-emerald-300 text-emerald-800",
    chip: "bg-emerald-100 text-emerald-800",
    Icono: CheckCircle2,
  },
  FALTANTE: {
    titulo: "FALTANTE",
    caja: "bg-rose-50 border-rose-300 text-rose-800",
    chip: "bg-rose-100 text-rose-800",
    Icono: AlertTriangle,
  },
  SOBRANTE: {
    titulo: "SOBRANTE",
    caja: "bg-amber-50 border-amber-300 text-amber-800",
    chip: "bg-amber-100 text-amber-800",
    Icono: TrendingUp,
  },
  // Cuentas en 0 (por ejemplo, justo después de GUARDAR REGISTRO): aún no hay conteo.
  SIN_VALORES: {
    titulo: "SIN VALORES REGISTRADOS",
    caja: "bg-slate-50 border-slate-200 text-slate-700",
    chip: "bg-slate-100 text-slate-700",
    Icono: Info,
  },
};

const textoResultado = (resultado, diferencia) => {
  if (resultado === "CUADRADA" || resultado === "SIN_VALORES") return ESTADOS[resultado].titulo;
  return `${ESTADOS[resultado]?.titulo || resultado} DE ${formatMoney(Math.abs(num(diferencia)))}`;
};

const diferenciaTexto = (d) => `${num(d) > 0 ? "+" : num(d) < 0 ? "-" : ""}${formatMoney(Math.abs(num(d)))}`;

const fechaHora = (valor) => new Date(valor).toLocaleString("es-CO", {
  year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
});

// Base de cálculo: total de fondos (caja + dinero prestado). El dinero prestado no se descuenta.
const ETIQUETAS_DESGLOSE = [
  ["capital_total", "Capital total registrado (aportes netos, multas, eventos e intereses)", 1],
  ["gastos_generales", "Gastos generales registrados", -1],
  ["liquidaciones_pagadas", "Liquidaciones ya pagadas a socios", -1],
];

export const Contabilidad = () => {
  const { user } = useAuth();
  const isAdmin = !!(user?.is_admin || user?.is_developer); // El Desarrollador también tiene acceso total.
  const [actual, setActual] = useState(null);
  const [registros, setRegistros] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pendientes, setPendientes] = useState(0);
  const [guardando, setGuardando] = useState(false);
  const [observacion, setObservacion] = useState("");
  const [abierto, setAbierto] = useState(null);
  const [verDesglose, setVerDesglose] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setError("");
      const [a, r] = await Promise.all([api.get("/contabilidad"), api.get("/contabilidad/registros")]);
      setActual(a.data);
      setRegistros(r.data);
    } catch (err) {
      console.error(err);
      setError("No se pudo cargar la contabilidad.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  const guardarRegistro = async () => {
    if (pendientes > 0) {
      alert("Hay líneas sin guardar. Guárdalas (✓) o descártalas antes de guardar el registro.");
      return;
    }
    if (!actual?.cuentas?.length) {
      alert("Agrega al menos una cuenta antes de guardar el registro.");
      return;
    }
    if (num(actual.total_cuentas) === 0) {
      alert("Escribe los valores de las cuentas antes de guardar el registro.");
      return;
    }
    if (!window.confirm(
      `¿Guardar el registro contable de este momento?\n\n` +
      `Después de guardar, las cuentas se mantienen pero sus valores vuelven a 0.\n\n` +
      `Dinero que debería existir: ${formatMoney(actual.dinero_esperado)}\n` +
      `Dinero en cuentas: ${formatMoney(actual.total_cuentas)}\n` +
      `Resultado: ${textoResultado(actual.resultado, actual.diferencia)}`
    )) return;
    try {
      setGuardando(true);
      const { data } = await api.post("/contabilidad/registros", { observacion: observacion.trim() || undefined });
      setObservacion("");
      await cargar();
      setAbierto(data.id);
    } catch (err) {
      alert(err?.response?.data?.detail || "No se pudo guardar el registro.");
    } finally {
      setGuardando(false);
    }
  };

  // Resultado en vivo: usa las líneas como están en pantalla, así al borrar una cuenta
  // o cambiar/borrar un valor el total, la diferencia y el estado cambian de inmediato.
  const [lineasVivas, setLineasVivas] = useState(null);
  const totalVivo = lineasVivas
    ? Math.round(lineasVivas.reduce((s, l) => s + (Number.isFinite(num(l.valor)) ? num(l.valor) : 0), 0) * 100) / 100
    : num(actual?.total_cuentas);
  const sinValores = totalVivo === 0;
  const diferenciaViva = sinValores ? 0 : Math.round((totalVivo - num(actual?.dinero_esperado)) * 100) / 100;
  const resultadoVivo = sinValores ? "SIN_VALORES" : diferenciaViva === 0 ? "CUADRADA" : diferenciaViva < 0 ? "FALTANTE" : "SOBRANTE";
  const estado = actual ? ESTADOS[resultadoVivo] : null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl md:text-3xl font-black text-slate-800 tracking-tight flex items-center gap-2.5">
          <Scale className="w-7 h-7 text-emerald-600" />
          Contabilidad
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Registra dónde está guardado el dinero y compáralo con el dinero que debería existir según el sistema.
        </p>
      </div>

      {loading ? (
        <div className="py-16 text-center text-slate-400 text-sm">
          <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
          Calculando contabilidad...
        </div>
      ) : error ? (
        <div className="p-6 bg-rose-50 border border-rose-200 rounded-2xl text-rose-700 text-sm">
          <p className="font-bold flex items-center gap-2"><AlertTriangle className="w-5 h-5" /> {error}</p>
          <button onClick={cargar} className="mt-3 px-4 py-2 bg-rose-600 text-white rounded-xl text-xs font-bold">Reintentar</button>
        </div>
      ) : actual && (
        <>
          {/* 3.1 Dinero total de los fondos (calculado desde los registros del sistema) */}
          <div className="bg-gradient-to-r from-slate-800 to-slate-700 rounded-2xl p-6 text-white shadow-sm">
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
              <div>
                <p className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                  <Landmark className="w-4 h-4" /> Dinero total de los fondos
                </p>
                <p className="text-4xl md:text-5xl font-black mt-1">{formatMoney(actual.dinero_esperado)}</p>
                <p className="text-xs text-slate-300 mt-1">Según los registros financieros del sistema (en caja y prestado)</p>
              </div>
              <button
                type="button"
                onClick={() => setVerDesglose((v) => !v)}
                className="self-start sm:self-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-xs font-bold"
              >
                <Info className="w-3.5 h-3.5" /> ¿Cómo se calcula? {verDesglose ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
            </div>
            {verDesglose && (
              <div className="mt-4 pt-4 border-t border-white/15 space-y-1.5 text-sm">
                {ETIQUETAS_DESGLOSE.map(([clave, texto, signo]) => (
                  <div key={clave} className="flex justify-between gap-3">
                    <span className="text-slate-300">{signo < 0 ? "− " : ""}{texto}</span>
                    <span className="font-bold whitespace-nowrap">{formatMoney(actual.desglose[clave])}</span>
                  </div>
                ))}
                <div className="flex justify-between gap-3 pt-1.5 border-t border-white/15">
                  <span className="font-bold">= Dinero que debería existir</span>
                  <span className="font-black whitespace-nowrap">{formatMoney(actual.desglose.dinero_esperado)}</span>
                </div>
                <p className="text-xs text-slate-300 pt-1">
                  Incluye el dinero prestado ({formatMoney(actual.desglose.cartera_prestada)}): sigue siendo parte de los fondos y no se descuenta.
                </p>
              </div>
            )}
          </div>

          {/* 3.2 Cuentas */}
          <section className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-4 sm:p-5">
            <h2 className="font-bold text-slate-800 mb-3">¿Dónde está el dinero? ({actual.cuentas.length})</h2>
            <LineasEditables
              items={actual.cuentas}
              campoNombre="nombre"
              etiquetaNombre="Cuenta o lugar"
              etiquetaValor="Valor disponible"
              placeholderNombre="Ej. Cuenta bancaria, efectivo, cuenta de ahorros..."
              textoBoton="NUEVO INGRESO"
              vacio="Aún no hay cuentas. Agrega dónde está guardado el dinero."
              editable={isAdmin}
              color="emerald"
              onPendientesChange={setPendientes}
              onLineasChange={setLineasVivas}
              onCrear={async (nombre, valor) => { await api.post("/contabilidad/cuentas", { nombre, valor }); await cargar(); }}
              onGuardar={async (id, nombre, valor) => { await api.put(`/contabilidad/cuentas/${id}`, { nombre, valor }); await cargar(); }}
              onEliminar={async (id) => { await api.delete(`/contabilidad/cuentas/${id}`); await cargar(); }}
            />

            {/* 3.3 Resultado */}
            <div className={`mt-5 rounded-2xl border-2 p-5 ${estado.caja}`}>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
                <div>
                  <p className="text-xs font-bold uppercase tracking-wider opacity-70">Debería existir</p>
                  <p className="text-lg font-black">{formatMoney(actual.dinero_esperado)}</p>
                </div>
                <div>
                  <p className="text-xs font-bold uppercase tracking-wider opacity-70">Registrado en cuentas</p>
                  <p className="text-lg font-black">{formatMoney(totalVivo)}</p>
                </div>
                <div>
                  <p className="text-xs font-bold uppercase tracking-wider opacity-70">Diferencia</p>
                  <p className="text-lg font-black">{diferenciaTexto(diferenciaViva)}</p>
                </div>
              </div>
              <p className="mt-4 text-xl md:text-2xl font-black flex items-center gap-2">
                <estado.Icono className="w-6 h-6" />
                {textoResultado(resultadoVivo, diferenciaViva)}
              </p>
              {pendientes > 0 && (
                <p className="mt-2 text-[11px] font-semibold">Incluye {pendientes} línea{pendientes === 1 ? "" : "s"} sin guardar: guárdala{pendientes === 1 ? "" : "s"} (✓) antes de GUARDAR REGISTRO.</p>
              )}
            </div>

            {/* 3.4 Guardar registro */}
            {isAdmin && (
              <div className="mt-4 flex flex-col sm:flex-row gap-2">
                <input
                  type="text"
                  maxLength={500}
                  value={observacion}
                  onChange={(e) => setObservacion(e.target.value)}
                  placeholder="Observación (opcional)"
                  className="flex-1 px-3 py-2.5 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
                />
                <button
                  type="button"
                  onClick={guardarRegistro}
                  disabled={guardando}
                  className="inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-black rounded-xl shadow-md shadow-emerald-600/20 disabled:opacity-50"
                >
                  <Save className="w-4 h-4" /> {guardando ? "GUARDANDO..." : "GUARDAR REGISTRO"}
                </button>
              </div>
            )}
          </section>

          {/* 3.5 Historial */}
          <section className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
              <History className="w-5 h-5 text-slate-500" />
              <h2 className="font-bold text-slate-800">Historial de registros contables ({registros.length})</h2>
            </div>
            {registros.length === 0 ? (
              <p className="py-10 text-center text-sm text-slate-400">Todavía no hay registros guardados.</p>
            ) : (
              <div className="divide-y divide-slate-100">
                <div className="hidden md:grid grid-cols-[1.3fr_1fr_1fr_1fr_1.3fr_24px] gap-3 px-5 py-2 text-[11px] font-bold text-slate-400 uppercase tracking-wider bg-slate-50/60">
                  <span>Fecha</span><span className="text-right">Esperado</span><span className="text-right">Contabilizado</span>
                  <span className="text-right">Diferencia</span><span>Estado</span><span />
                </div>
                {registros.map((r) => {
                  const e = ESTADOS[r.resultado] || ESTADOS.CUADRADA;
                  const expandido = abierto === r.id;
                  return (
                    <div key={r.id}>
                      <button
                        type="button"
                        onClick={() => setAbierto(expandido ? null : r.id)}
                        aria-expanded={expandido}
                        className="w-full text-left px-5 py-3 grid grid-cols-2 md:grid-cols-[1.3fr_1fr_1fr_1fr_1.3fr_24px] gap-x-3 gap-y-1 items-center text-sm hover:bg-slate-50/60"
                      >
                        <span className="font-bold text-slate-700">{fechaHora(r.fecha_registro)}</span>
                        <span className="md:text-right text-slate-600"><span className="md:hidden text-[11px] text-slate-400">Esperado: </span>{formatMoney(r.dinero_esperado)}</span>
                        <span className="md:text-right text-slate-600"><span className="md:hidden text-[11px] text-slate-400">Contado: </span>{formatMoney(r.total_cuentas)}</span>
                        <span className="md:text-right font-bold text-slate-700"><span className="md:hidden text-[11px] text-slate-400 font-normal">Diferencia: </span>{diferenciaTexto(r.diferencia)}</span>
                        <span><span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${e.chip}`}>{textoResultado(r.resultado, r.diferencia)}</span></span>
                        <span className="text-slate-400 justify-self-end">{expandido ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}</span>
                      </button>
                      {expandido && (
                        <div className="px-5 pb-4">
                          <div className="rounded-xl bg-slate-50 border border-slate-100 p-4 text-sm space-y-3">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="text-left text-[11px] text-slate-400 uppercase tracking-wider">
                                  <th className="py-1 font-bold">Cuenta</th>
                                  <th className="py-1 font-bold text-right">Valor</th>
                                </tr>
                              </thead>
                              <tbody>
                                {r.cuentas.map((c) => (
                                  <tr key={c.orden} className="border-t border-slate-100">
                                    <td className="py-1.5 text-slate-700">{c.nombre}</td>
                                    <td className="py-1.5 text-right font-semibold text-slate-800">{formatMoney(c.valor)}</td>
                                  </tr>
                                ))}
                              </tbody>
                              <tfoot>
                                <tr className="border-t-2 border-slate-200">
                                  <td className="py-1.5 font-black text-slate-800">Total en cuentas</td>
                                  <td className="py-1.5 text-right font-black text-slate-800">{formatMoney(r.total_cuentas)}</td>
                                </tr>
                                <tr>
                                  <td className="py-1 text-slate-500">Dinero que debería existir</td>
                                  <td className="py-1 text-right text-slate-600">{formatMoney(r.dinero_esperado)}</td>
                                </tr>
                                <tr>
                                  <td className="py-1 text-slate-500">Diferencia</td>
                                  <td className="py-1 text-right font-bold text-slate-700">{diferenciaTexto(r.diferencia)}</td>
                                </tr>
                              </tfoot>
                            </table>
                            {r.desglose_esperado && (
                              <p className="text-[11px] text-slate-400">
                                Esperado al guardar: capital {formatMoney(r.desglose_esperado.capital_total)}
                                {/* Registros anteriores al cambio descontaban el dinero prestado: se muestran como se guardaron. */}
                                {r.desglose_esperado.base_calculo !== "TOTAL_FONDOS" && <> − prestado {formatMoney(r.desglose_esperado.cartera_prestada)}</>}
                                {" "}− gastos {formatMoney(r.desglose_esperado.gastos_generales)} − liquidaciones {formatMoney(r.desglose_esperado.liquidaciones_pagadas)}
                              </p>
                            )}
                            {(r.observacion || r.usuario_nombre) && (
                              <p className="text-xs text-slate-500">
                                {r.observacion && <span className="italic">"{r.observacion}"</span>}
                                {r.usuario_nombre && <span> · Guardado por {r.usuario_nombre}</span>}
                              </p>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
};
