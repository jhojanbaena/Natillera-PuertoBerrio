import React, { useMemo, useState } from "react";
import { Check, ChevronLeft, ChevronRight, AlertTriangle } from "lucide-react";
import api from "../api/client";
import { formatMoney, formatDate, fechaLocalISO } from "../utils/formatters";

// Lista tipo "Notas" con los intereses de cada mes.
// - Regla vigente (10 %: 7 % socio / 3 % bien común): un solo botón con el valor del mes,
//   calculado sobre el capital pendiente.
// - Regla anterior 7 % / 10 %: se elige la tasa.
// Al confirmar se registra el abono de interés en el préstamo (detalle e historial).

const MESES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

const num = (v) => Number(v || 0);
const pct = (v) => `${num(v).toLocaleString("es-CO", { maximumFractionDigits: 2 })} %`;
const redondear = (v) => Math.round(v * 100) / 100;
const mesDe = (fechaISO) => fechaISO.slice(0, 7);
const claveMes = (anio, mes) => `${anio}-${String(mes + 1).padStart(2, "0")}`;

const mensajeError = (err, porDefecto) => {
  const detalle = err.response?.data?.detail;
  if (typeof detalle === "string") return detalle;
  if (Array.isArray(detalle)) return detalle.map((d) => d.msg).join("\n");
  return porDefecto;
};

const Circulo = ({ pagado, ocupado }) => (
  <span
    className={`mt-0.5 w-5 h-5 shrink-0 rounded-full border-2 flex items-center justify-center transition-colors ${
      pagado
        ? "bg-emerald-500 border-emerald-500 text-white"
        : ocupado
        ? "border-purple-400 animate-pulse"
        : "border-slate-300"
    }`}
  >
    {pagado && <Check className="w-3 h-3" strokeWidth={3} />}
  </span>
);

const REGLAS_MES = ["MORA_7_10", "REPARTO_7_3"];
const esReparto = (p) => p.regla_interes === "REPARTO_7_3";

/** Convierte los préstamos con intereses mes a mes en una línea por cuota. */
const construirLineas = (prestamos, socios) => {
  const nombre = (id) => socios.find((s) => s.id === id)?.nombre || `Socio #${id}`;
  const lineas = [];
  prestamos.forEach((p) => {
    if (!REGLAS_MES.includes(p.regla_interes)) return;
    (p.periodos || []).forEach((m) => {
      const abonos = (p.abonos || []).filter((a) => a.numero_cuota === m.numero_cuota && num(a.monto_interes) > 0);
      const tasas = abonos.map((a) => num(a.tasa_aplicada)).filter(Boolean);
      lineas.push({
        clave: `${p.id}-${m.numero_cuota}`,
        prestamo: p,
        socio: nombre(p.socio_id),
        cuota: m.numero_cuota,
        fechaLimite: m.fecha_limite,
        pagado: num(m.pagado),
        pendiente: num(m.pendiente),
        tasaFinal: num(m.tasa),
        tasaPrevia: tasas.length ? Math.max(...tasas) : 0,
        completo: m.estado === "PAGADO",
        destino: m.destino,
        base: num(m.base) || num(p.monto_prestado),
        interesSocio: num(m.interes_socio),
        interesBienComun: num(m.interes_bien_comun),
        ultimoAbono: abonos[abonos.length - 1],
      });
    });
  });
  return lineas.sort((a, b) => a.fechaLimite.localeCompare(b.fechaLimite) || a.socio.localeCompare(b.socio));
};

export const InteresesMes = ({ prestamos, socios, onRegistrado }) => {
  const hoy = fechaLocalISO();
  const [anio, setAnio] = useState(() => Number(hoy.slice(0, 4)));
  const [mes, setMes] = useState(() => Number(hoy.slice(5, 7)) - 1);
  const [fechas, setFechas] = useState({});
  const [guardando, setGuardando] = useState(null);

  const lineas = useMemo(() => construirLineas(prestamos, socios), [prestamos, socios]);
  const clave = claveMes(anio, mes);
  const delMes = lineas.filter((l) => mesDe(l.fechaLimite) === clave);
  // Cuotas de meses anteriores que siguen sin pagar: se muestran arriba para no olvidarlas.
  const atrasadas = lineas.filter((l) => mesDe(l.fechaLimite) < clave && !l.completo);

  const totalMes = delMes.reduce((s, l) => s + l.pagado, 0);
  const pagadasMes = delMes.filter((l) => l.completo).length;

  const moverMes = (paso) => {
    const total = anio * 12 + mes + paso;
    setAnio(Math.floor(total / 12));
    setMes(total % 12);
  };

  const fechaDe = (l) => fechas[l.clave] || hoy;

  const montoSegunTasa = (l, tasa) => {
    // Si ya se abonó parte a otra tasa, el mes queda con la tasa más alta elegida.
    const tasaMes = Math.max(tasa, l.tasaPrevia);
    return Math.max(0, redondear(l.base * tasaMes / 100 - l.pagado));
  };

  const registrar = async (l, tasa) => {
    if (guardando) return;
    const fecha = fechaDe(l);
    const monto = montoSegunTasa(l, tasa);
    if (!fecha) return alert("Elige la fecha del pago.");
    if (monto <= 0) return alert("Esta cuota no tiene interés pendiente a esa tasa.");
    const sugerida = fecha <= l.fechaLimite ? num(l.prestamo.tasa_interes) : num(l.prestamo.tasa_mora || 10);
    const aviso = !esReparto(l.prestamo) && tasa !== sugerida ? `\n\nOjo: por la fecha correspondería ${pct(sugerida)}.` : "";
    if (!window.confirm(
      `¿Registrar el interés de ${l.socio}?\n\n` +
      `Préstamo #${l.prestamo.id} · Cuota #${l.cuota} (vence ${formatDate(l.fechaLimite)})\n` +
      `Tasa: ${pct(tasa)} · Valor: ${formatMoney(monto)} · Fecha de pago: ${formatDate(fecha)}${aviso}`
    )) return;

    try {
      setGuardando(l.clave);
      await api.post(`/prestamos/${l.prestamo.id}/abonos`, {
        prestamo_id: l.prestamo.id,
        monto_abonado: monto.toFixed(2),
        monto_capital: "0.00",
        monto_interes: monto.toFixed(2),
        numero_cuota: l.cuota,
        tasa_aplicada: String(tasa),
        fecha_pago: fecha,
      });
      setFechas(({ [l.clave]: _omitida, ...resto }) => resto);
      await onRegistrado();
    } catch (err) {
      alert(mensajeError(err, "Error al registrar el interés."));
      await onRegistrado();
    } finally {
      setGuardando(null);
    }
  };

  const renderLinea = (l) => {
    const fecha = fechaDe(l);
    const atrasada = fecha > l.fechaLimite;
    const ocupado = guardando === l.clave;
    const normal = num(l.prestamo.tasa_interes);
    const mora = num(l.prestamo.tasa_mora || 10);
    const bloqueado = l.prestamo.estado === "PAGADO";
    return (
      <li className={`flex items-start gap-3 px-4 py-2.5 text-xs ${l.completo ? "bg-emerald-50/30" : ""} ${ocupado ? "opacity-60 pointer-events-none" : ""}`}>
        <Circulo pagado={l.completo} ocupado={ocupado} />
        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
            <span className={`font-semibold ${l.completo ? "text-slate-400 line-through decoration-emerald-400" : "text-slate-800"}`}>
              {l.socio}
            </span>
            <span className="text-slate-400">Préstamo #{l.prestamo.id} · Cuota #{l.cuota}</span>
            <span className={!l.completo && l.fechaLimite < hoy ? "text-rose-600 font-semibold" : "text-slate-400"}>
              Vence {formatDate(l.fechaLimite)}
            </span>
            <span className="text-slate-400">
              {l.destino === "REPARTO_7_3"
                ? `→ Socio ${formatMoney(l.interesSocio)} · Bien común ${formatMoney(l.interesBienComun)}`
                : l.destino === "BIEN_COMUN" ? "→ Bien común" : "→ Ahorro personal"}
            </span>
          </div>

          {l.completo ? (
            <p className="text-slate-500">
              Pagado <strong className="text-slate-700">{formatMoney(l.pagado)}</strong> al{" "}
              <strong className={l.tasaFinal > normal ? "text-rose-700" : "text-emerald-700"}>{pct(l.tasaFinal)}</strong>
              {l.ultimoAbono && <> · {formatDate(l.ultimoAbono.fecha_pago)}</>}
            </p>
          ) : bloqueado ? (
            <p className="text-slate-400 italic">Préstamo pagado</p>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="date"
                value={fecha}
                onChange={(e) => setFechas((prev) => ({ ...prev, [l.clave]: e.target.value }))}
                aria-label={`Fecha de pago de ${l.socio}, cuota ${l.cuota}`}
                className="bg-transparent border-0 border-b border-dashed border-slate-300 focus:border-purple-500 focus:outline-none focus:ring-0 px-0.5 py-0.5 text-xs text-slate-700 w-32"
              />
              {(esReparto(l.prestamo) ? [normal] : [normal, mora]).map((tasa) => {
                const sugerida = esReparto(l.prestamo) || (tasa === mora) === atrasada;
                return (
                  <button
                    key={tasa}
                    type="button"
                    onClick={() => registrar(l, tasa)}
                    title={sugerida ? "Tasa que corresponde por la fecha" : "Elegir esta tasa de todas formas"}
                    className={`px-2.5 py-1 rounded-full border font-bold transition-colors ${
                      tasa === mora && !esReparto(l.prestamo)
                        ? sugerida
                          ? "bg-rose-600 border-rose-600 text-white hover:bg-rose-700"
                          : "border-rose-200 text-rose-700 hover:bg-rose-50"
                        : sugerida
                        ? "bg-emerald-600 border-emerald-600 text-white hover:bg-emerald-700"
                        : "border-emerald-200 text-emerald-700 hover:bg-emerald-50"
                    }`}
                  >
                    {pct(tasa)} · {formatMoney(montoSegunTasa(l, tasa))}
                  </button>
                );
              })}
              {l.pagado > 0 && <span className="text-slate-400">Ya abonado {formatMoney(l.pagado)}</span>}
            </div>
          )}
        </div>
        <span
          className={`shrink-0 px-2 py-0.5 rounded-full text-[10px] font-bold ${
            l.completo
              ? "bg-emerald-50 text-emerald-700"
              : l.fechaLimite < hoy
              ? "bg-rose-50 text-rose-700"
              : "bg-amber-50 text-amber-700"
          }`}
        >
          {l.completo ? "Pagado" : l.fechaLimite < hoy ? "En mora" : "Pendiente"}
        </span>
      </li>
    );
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-100">
        <p className="text-sm font-bold text-purple-800">Intereses del mes</p>
        <p className="text-[11px] text-slate-400 mt-0.5">
          Registra el pago del interés de cada línea. Préstamos vigentes: 10 % del capital pendiente (7 % socio / 3 % bien común).
          Préstamos con la regla anterior: elige 7 % o 10 %; la tasa resaltada es la que corresponde por la fecha.
        </p>
      </div>

      <div className="flex items-center justify-between px-4 py-2 bg-slate-50/60">
        <button type="button" onClick={() => moverMes(-1)} className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-white" title="Mes anterior">
          <ChevronLeft className="w-4 h-4" />
        </button>
        <div className="text-center">
          <p className="text-xs font-bold text-slate-600">{MESES[mes]} {anio}</p>
          <p className="text-[11px] text-slate-400">{pagadasMes}/{delMes.length} pagadas · {formatMoney(totalMes)} cobrado</p>
        </div>
        <button type="button" onClick={() => moverMes(1)} className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-white" title="Mes siguiente">
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>

      {atrasadas.length > 0 && (
        <>
          <p className="px-4 py-2 text-[11px] font-bold text-rose-700 bg-rose-50/60 border-y border-rose-100 flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5" /> Pendientes de meses anteriores ({atrasadas.length})
          </p>
          <ul className="divide-y divide-slate-100">
            {atrasadas.map((l) => <React.Fragment key={l.clave}>{renderLinea(l)}</React.Fragment>)}
          </ul>
        </>
      )}

      {delMes.length > 0 ? (
        <ul className="divide-y divide-slate-100 border-t border-slate-100">
          {delMes.map((l) => <React.Fragment key={l.clave}>{renderLinea(l)}</React.Fragment>)}
        </ul>
      ) : (
        <p className="px-4 py-8 text-center text-xs text-slate-400">No hay intereses que venzan en {MESES[mes].toLowerCase()} de {anio}.</p>
      )}

      <p className="px-4 py-2.5 text-[11px] text-slate-400 bg-slate-50/60 border-t border-slate-100">
        Aparecen los préstamos con intereses mes a mes. Los de tasa fija se abonan desde la pestaña Cartera.
      </p>
    </div>
  );
};
