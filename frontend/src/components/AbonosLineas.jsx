import React, { useEffect, useRef, useState } from "react";
import { Check, Edit, Plus, X } from "lucide-react";
import api from "../api/client";
import { MoneyInput } from "./MoneyInput";
import { formatMoney, formatDate, fechaLocalISO } from "../utils/formatters";

// Abonos de un préstamo como lista tipo "aportes mensuales": cada abono guardado
// es una línea pagada y al final se agregan líneas nuevas (capital, interés,
// fecha). Tocar una línea nueva registra el abono (con confirmación).

const num = (v) => Number(v || 0);
const esRegla = (p) => p?.regla_interes === "MORA_7_10" || p?.regla_interes === "REPARTO_7_3";
let secuencia = 0;
const nuevaClave = () => `linea-${++secuencia}`;

const mensajeError = (err, porDefecto) => {
  const detalle = err.response?.data?.detail;
  if (typeof detalle === "string") return detalle;
  if (Array.isArray(detalle)) return detalle.map((d) => d.msg).join("\n");
  return porDefecto;
};

const inputClase =
  "bg-transparent border-0 border-b border-dashed border-slate-300 focus:border-purple-500 focus:outline-none focus:ring-0 px-0.5 py-0.5 text-xs text-slate-700";

// Evita que escribir en un campo de la línea dispare el registro del abono.
const esCampo = (e) => e.target.closest("input, select, textarea, label, button");

const Circulo = ({ pagado, ocupado }) => (
  <span
    className={`w-5 h-5 shrink-0 rounded-full border-2 flex items-center justify-center transition-colors ${
      pagado
        ? "bg-emerald-500 border-emerald-500 text-white"
        : ocupado
        ? "border-purple-400 animate-pulse"
        : "border-slate-300 group-hover:border-purple-500"
    }`}
  >
    {pagado && <Check className="w-3 h-3" strokeWidth={3} />}
  </span>
);

const Estado = ({ pagado }) => (
  <span
    className={`shrink-0 text-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
      pagado ? "bg-emerald-50 text-emerald-700" : "bg-purple-50 text-purple-700"
    }`}
  >
    {pagado ? "Pagada" : "Nueva"}
  </span>
);

// Mismas columnas en el encabezado y en cada línea.
const FILA =
  "grid grid-cols-[20px_minmax(118px,1.2fr)_104px_minmax(90px,1fr)_minmax(90px,1fr)_minmax(120px,1.1fr)_56px_24px] items-center gap-x-3 px-4";

const pct = (v) => `${num(v).toLocaleString("es-CO", { maximumFractionDigits: 2 })} %`;

// Interés pendiente de la cuota según la tasa elegida (7 % a tiempo o 10 % con retraso).
const pendienteSegun = (data, tasa) =>
  num(num(tasa) === num(data.tasa_mora) ? data.pendiente_tasa_mora : data.pendiente_tasa_normal);

// `tasa` null = la sugerida por la fecha; `tasaElegida` = el administrador eligió otra.
const lineaNueva = () => ({
  clave: nuevaClave(), capital: "0", interes: "0", fecha: fechaLocalISO(),
  tasa: null, tasaElegida: false, interesEditado: false,
});

export const AbonosLineas = ({ prestamo, onRegistrado, onEditar, lineaInicial = false }) => {
  const [lineas, setLineas] = useState(() => (lineaInicial && prestamo.estado !== "PAGADO" ? [lineaNueva()] : []));
  const [previas, setPrevias] = useState({});
  const [guardando, setGuardando] = useState(null);
  const cerrado = prestamo.estado === "PAGADO";
  const conRegla = esRegla(prestamo);

  const abonos = [...(prestamo.abonos || [])].sort(
    (a, b) => a.numero_cuota - b.numero_cuota || String(a.fecha_pago).localeCompare(String(b.fecha_pago)) || a.id - b.id
  );

  const editar = (clave, cambios) =>
    setLineas((prev) => prev.map((l) => (l.clave === clave ? { ...l, ...cambios } : l)));

  // Con regla de intereses, cada fecha define la cuota (o crea la siguiente) y el interés sugerido.
  const fechasClave = lineas.map((l) => `${l.clave}:${l.fecha}`).join("|");
  // Al registrar otro abono cambian las cuotas: las vistas previas se recalculan.
  const firma = (prestamo.abonos || []).map((a) => `${a.id}:${a.numero_cuota}`).join(",");
  // Una respuesta solo se aplica si la línea sigue con esa fecha y el préstamo con esos abonos.
  const firmaActual = useRef(firma);
  firmaActual.current = firma;
  useEffect(() => {
    if (!conRegla) return;
    lineas.forEach((l) => {
      const actual = previas[l.clave];
      if (!l.fecha || (actual?.fecha === l.fecha && actual?.firma === firma)) return;
      const { clave, fecha } = l;
      const vigente = () => firmaActual.current === firma;
      api.get(`/prestamos/${prestamo.id}/abonos/vista-previa`, { params: { fecha_pago: fecha } })
        .then(({ data }) => {
          if (!vigente()) return;
          setLineas((prev) => {
            const linea = prev.find((x) => x.clave === clave);
            if (!linea || linea.fecha !== fecha) return prev;
            setPrevias((p) => ({ ...p, [clave]: { fecha, firma, data } }));
            const tasa = linea.tasaElegida && linea.tasa != null ? linea.tasa : String(num(data.tasa_sugerida));
            const interes = linea.interesEditado ? linea.interes : String(pendienteSegun(data, tasa));
            return prev.map((x) => (x.clave === clave ? { ...x, tasa, interes } : x));
          });
        })
        .catch((err) => {
          if (vigente()) setPrevias((p) => ({ ...p, [clave]: { fecha, firma, error: mensajeError(err, "No se pudo calcular la cuota") } }));
        });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fechasClave, conRegla, prestamo.id, firma]);

  const elegirTasa = (linea, data, tasa) =>
    editar(linea.clave, {
      tasa: String(num(tasa)), tasaElegida: true, interesEditado: false,
      interes: String(pendienteSegun(data, tasa)),
    });

  const quitar = (clave) => {
    setLineas((prev) => prev.filter((l) => l.clave !== clave));
    setPrevias(({ [clave]: _omitida, ...resto }) => resto);
  };

  const registrar = async (linea) => {
    if (guardando) return;
    const capital = num(linea.capital);
    const interes = num(linea.interes);
    const previa = previas[linea.clave]?.fecha === linea.fecha ? previas[linea.clave]?.data : null;
    if (capital + interes <= 0) return alert("Escribe el capital o el interés del abono.");
    if (!linea.fecha) return alert("Escribe la fecha del abono.");
    if (conRegla && !previa) return alert("Espera a que se calcule la cuota de esta fecha.");
    const tasa = previa ? (linea.tasa ?? String(num(previa.tasa_sugerida))) : null;
    const cuotaTxt = previa ? ` a la cuota #${previa.numero_cuota}${previa.cuota_nueva ? " (nueva)" : ""}` : "";
    const tasaTxt = tasa != null && interes > 0 ? ` al ${pct(tasa)}` : "";
    if (!window.confirm(
      `¿Registrar abono${cuotaTxt} del ${formatDate(linea.fecha)}?\n\nCapital: ${formatMoney(capital)}\nInterés${tasaTxt}: ${formatMoney(interes)}\nTotal: ${formatMoney(capital + interes)}`
    )) return;

    try {
      setGuardando(linea.clave);
      await api.post(`/prestamos/${prestamo.id}/abonos`, {
        prestamo_id: prestamo.id,
        monto_abonado: (capital + interes).toFixed(2),
        monto_capital: capital.toFixed(2),
        monto_interes: interes.toFixed(2),
        fecha_pago: linea.fecha,
        numero_cuota: previa?.numero_cuota,
        tasa_aplicada: tasa != null && interes > 0 ? tasa : undefined,
      });
      quitar(linea.clave);
      await onRegistrado();
    } catch (err) {
      alert(mensajeError(err, "Error al registrar el abono."));
    } finally {
      setGuardando(null);
    }
  };

  const totalCapital = abonos.reduce((s, a) => s + num(a.monto_capital), 0);
  const totalInteres = abonos.reduce((s, a) => s + num(a.monto_interes), 0);

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white overflow-hidden">
      <div className="overflow-x-auto">
      <div className="min-w-[720px]">
      <div className={`${FILA} py-2 bg-slate-50/60 text-[10px] font-bold uppercase tracking-wider text-slate-400`}>
        <span />
        <span>Cuota</span>
        <span>Tasa</span>
        <span>Capital</span>
        <span>Interés</span>
        <span>Fecha</span>
        <span className="text-center">Estado</span>
        <span />
      </div>

      <ul className="divide-y divide-slate-100">
        {abonos.map((ab) => (
          <li key={ab.id} className={`${FILA} py-2.5 text-xs bg-emerald-50/30`}>
            <Circulo pagado />
            <span className="font-semibold text-slate-400 line-through decoration-emerald-400 whitespace-nowrap">Cuota #{ab.numero_cuota}</span>
            <span className="text-slate-500 font-semibold">{ab.tasa_aplicada != null ? pct(ab.tasa_aplicada) : "—"}</span>
            <span className="font-bold text-slate-600">{formatMoney(ab.monto_capital)}</span>
            <span className="font-bold text-slate-600">{formatMoney(ab.monto_interes)}</span>
            <span className="text-slate-400 whitespace-nowrap">{formatDate(ab.fecha_pago)}</span>
            <Estado pagado />
            <button
              type="button"
              onClick={() => onEditar(ab)}
              title="Editar abono"
              aria-label={`Editar abono ${ab.id}`}
              className="inline-flex justify-center p-1 text-slate-400 hover:text-purple-600 hover:bg-purple-50 rounded"
            >
              <Edit className="w-3 h-3" />
            </button>
          </li>
        ))}

        {lineas.map((l) => {
          const previa = previas[l.clave]?.fecha === l.fecha ? previas[l.clave] : null;
          const ocupado = guardando === l.clave;
          return (
            <li
              key={l.clave}
              onClick={(e) => !esCampo(e) && registrar(l)}
              title="Toca la línea para registrar el abono"
              className={`group ${FILA} py-2.5 text-xs cursor-pointer hover:bg-slate-50 ${ocupado ? "opacity-60 pointer-events-none" : ""}`}
            >
              <Circulo ocupado={ocupado} />
              <span className="min-w-0 font-semibold text-slate-800 leading-tight">
                {!conRegla ? "Nuevo abono" : previa?.data ? (
                  <>
                    Cuota #{previa.data.numero_cuota}
                    {previa.data.cuota_nueva ? (
                      <span className="mt-0.5 flex flex-wrap items-center gap-1 text-[10px] font-normal text-slate-400">
                        <span className="px-1.5 py-px rounded-full bg-purple-100 text-purple-700 font-bold">nueva</span>
                        <span className="whitespace-nowrap">vence {formatDate(previa.data.fecha_limite)}</span>
                      </span>
                    ) : num(previa.data.interes_pagado) > 0 && num(num(previa.data.tasa_sugerida) === num(previa.data.tasa_mora) ? previa.data.pendiente_tasa_mora : previa.data.pendiente_tasa_normal) === 0 ? (
                      <span className="block mt-0.5 text-[10px] font-normal text-slate-400">interés al día · solo capital</span>
                    ) : (
                      <span className="block mt-0.5 text-[10px] font-normal text-slate-400 whitespace-nowrap">vence {formatDate(previa.data.fecha_limite)}</span>
                    )}
                  </>
                ) : previa?.error ? <span className="text-rose-600 text-[10px]">{previa.error}</span> : "…"}
              </span>
              <span className="flex items-center gap-1">
                {previa?.data ? (
                  [...new Set([num(previa.data.tasa_normal), num(previa.data.tasa_mora)])].map((t) => {
                    const activa = num(l.tasa ?? previa.data.tasa_sugerida) === t;
                    const sugerida = num(previa.data.tasa_sugerida) === t;
                    const mora = t > num(previa.data.tasa_normal);
                    return (
                      <button
                        key={t}
                        type="button"
                        onClick={() => elegirTasa(l, previa.data, t)}
                        title={sugerida ? "Tasa sugerida por la fecha" : "Elegir esta tasa"}
                        className={`px-2 py-0.5 rounded-full text-[11px] font-bold border whitespace-nowrap transition-colors ${
                          activa
                            ? mora ? "bg-rose-600 border-rose-600 text-white" : "bg-emerald-600 border-emerald-600 text-white"
                            : "bg-white border-slate-200 text-slate-500 hover:border-purple-300"
                        }`}
                      >
                        {pct(t)}{sugerida && !activa ? " •" : ""}
                      </button>
                    );
                  })
                ) : (
                  <span className="text-slate-300">—</span>
                )}
              </span>
              <label className="flex items-center gap-1 text-slate-400 min-w-0">
                $
                <MoneyInput
                  value={l.capital}
                  onChange={(e) => editar(l.clave, { capital: e.target.value })}
                  aria-label="Capital del abono"
                  className={`${inputClase} w-full font-bold`}
                />
              </label>
              <label className="flex items-center gap-1 text-slate-400 min-w-0">
                $
                <MoneyInput
                  value={l.interes}
                  onChange={(e) => editar(l.clave, { interes: e.target.value, interesEditado: true })}
                  aria-label="Interés del abono"
                  className={`${inputClase} w-full font-bold`}
                />
              </label>
              <span>
                <input
                  type="date"
                  value={l.fecha}
                  onChange={(e) => editar(l.clave, { fecha: e.target.value, tasaElegida: false, interesEditado: false })}
                  aria-label="Fecha del abono"
                  className={`${inputClase} w-full`}
                />
              </span>
              <Estado />
              <button
                type="button"
                onClick={() => quitar(l.clave)}
                title="Descartar línea"
                aria-label="Descartar línea"
                className="inline-flex justify-center p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded"
              >
                <X className="w-3 h-3" />
              </button>
            </li>
          );
        })}

        {abonos.length === 0 && lineas.length === 0 && (
          <li className="px-4 py-4 text-center text-xs text-slate-400 italic">Sin abonos registrados aún.</li>
        )}
      </ul>
      </div>
      </div>

      <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-slate-100 bg-slate-50/60">
        <button
          type="button"
          disabled={cerrado}
          onClick={() => setLineas((prev) => [...prev, lineaNueva()])}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold text-purple-700 bg-purple-50 hover:bg-purple-100 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Plus className="w-3.5 h-3.5" /> Agregar línea
        </button>
        <span className="text-[11px] text-slate-500">
          Pagado: capital <strong>{formatMoney(totalCapital)}</strong> · interés <strong>{formatMoney(totalInteres)}</strong>
        </span>
      </div>
    </div>
  );
};
