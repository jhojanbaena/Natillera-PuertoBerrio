import React, { useMemo, useState } from "react";
import { Check, ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import api from "../api/client";
import { RichTextDisplay } from "./RichTextField";
import { MoneyInput } from "./MoneyInput";
import { formatMoney, formatDate, fechaLocalISO } from "../utils/formatters";
import { anioDeTrabajo } from "../utils/periodo";

// Secciones tipo "Notas" del estado de cuenta del socio: una línea por aporte
// mensual o multa. Tocar una línea pendiente registra su pago (con confirmación).

const MESES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

const periodoDe = (anio, mes) => `${anio}-${String(mes + 1).padStart(2, "0")}`;

const textoPlano = (valor) => {
  if (!valor) return "";
  if (!/[<][a-z][\s\S]*[>]/i.test(valor)) return valor;
  return new DOMParser().parseFromString(valor, "text/html").body.textContent || "";
};

const montoValido = (valor) => Number.isFinite(Number(valor)) && Number(valor) > 0;

const mensajeError = (err, porDefecto) => {
  const detalle = err.response?.data?.detail;
  if (typeof detalle === "string") return detalle;
  if (Array.isArray(detalle)) return detalle.map((d) => d.msg).join("\n");
  return porDefecto;
};

const inputClase =
  "bg-transparent border-0 border-b border-dashed border-slate-300 focus:border-emerald-500 focus:outline-none focus:ring-0 px-0.5 py-0.5 text-xs text-slate-700";

const Seccion = ({ titulo, resumen, abierta, onToggle, children, acento }) => (
  <div className="rounded-2xl border border-slate-200/80 bg-white overflow-hidden">
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={abierta}
      className="w-full flex items-center justify-between gap-3 px-4 py-3 hover:bg-slate-50/70 transition-colors text-left"
    >
      <div className="min-w-0">
        <p className={`text-sm font-bold ${acento}`}>{titulo}</p>
        <p className="text-[11px] text-slate-400 mt-0.5 truncate">{resumen}</p>
      </div>
      <ChevronDown
        className={`w-4 h-4 text-slate-400 shrink-0 transition-transform duration-200 ${abierta ? "rotate-180" : ""}`}
      />
    </button>
    {abierta && <div className="border-t border-slate-100">{children}</div>}
  </div>
);

const Circulo = ({ pagado, ocupado }) => (
  <span
    className={`mt-0.5 w-5 h-5 shrink-0 rounded-full border-2 flex items-center justify-center transition-colors ${
      pagado
        ? "bg-emerald-500 border-emerald-500 text-white"
        : ocupado
        ? "border-emerald-400 animate-pulse"
        : "border-slate-300 group-hover:border-emerald-500"
    }`}
  >
    {pagado && <Check className="w-3 h-3" strokeWidth={3} />}
  </span>
);

const Estado = ({ pagado }) => (
  <span
    className={`shrink-0 px-2 py-0.5 rounded-full text-[10px] font-bold ${
      pagado ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"
    }`}
  >
    {pagado ? "Pagado" : "Pendiente"}
  </span>
);

// Evita que escribir en un campo de la línea dispare el registro del pago.
const esCampo = (e) => e.target.closest("input, select, textarea, label");

export const AportesMensuales = ({ socio, onRegistrado }) => {
  const [abierta, setAbierta] = useState(false);
  const [anio, setAnio] = useState(() => anioDeTrabajo());
  const [borradores, setBorradores] = useState({});
  const [guardando, setGuardando] = useState(null);

  const hoy = fechaLocalISO();
  const valorPactado = socio.aporte_mensual;

  const { porPeriodo, sinMes } = useMemo(() => {
    const porPeriodo = {};
    const sinMes = { cantidad: 0, total: 0 };
    (socio.historial_finanzas || []).forEach((m) => {
      if (m.tipo_movimiento !== "APORTE") return;
      if (m.periodo) {
        porPeriodo[m.periodo] = m;
      } else if (new Date(m.fecha).getFullYear() === anio) {
        sinMes.cantidad += 1;
        sinMes.total += Number(m.monto);
      }
    });
    return { porPeriodo, sinMes };
  }, [socio.historial_finanzas, anio]);

  const pagadosAnio = MESES.filter((_, i) => porPeriodo[periodoDe(anio, i)]);
  const totalAnio = MESES.reduce((suma, _, i) => suma + Number(porPeriodo[periodoDe(anio, i)]?.monto || 0), 0);

  const borrador = (periodo) => ({ monto: valorPactado, fecha: hoy, ...borradores[periodo] });
  const editar = (periodo, campo, valor) =>
    setBorradores((prev) => ({ ...prev, [periodo]: { ...borrador(periodo), ...prev[periodo], [campo]: valor } }));

  const registrar = async (mesIndex) => {
    const periodo = periodoDe(anio, mesIndex);
    if (porPeriodo[periodo] || guardando) return;
    const { monto, fecha } = borrador(periodo);
    const etiqueta = `${MESES[mesIndex]} ${anio}`;
    if (!montoValido(monto)) return alert("Escribe un valor mayor a cero para el aporte.");
    if (!fecha || fecha > hoy) return alert("La fecha del aporte no puede estar vacía ni ser futura.");
    if (!window.confirm(`¿Registrar como pagado el aporte de ${etiqueta} por ${formatMoney(monto)} con fecha ${formatDate(fecha)}?`)) return;

    try {
      setGuardando(periodo);
      await api.post(`/socios/${socio.id}/movimientos`, {
        tipo_movimiento: "APORTE",
        monto,
        fecha,
        periodo,
        descripcion: `Aporte mensual — ${etiqueta}`,
      });
      setBorradores((prev) => {
        const { [periodo]: _omitido, ...resto } = prev;
        return resto;
      });
      await onRegistrado();
    } catch (err) {
      console.error(err);
      alert(mensajeError(err, "Error al registrar el aporte."));
      await onRegistrado();
    } finally {
      setGuardando(null);
    }
  };

  return (
    <Seccion
      titulo="Aportes mensuales"
      acento="text-emerald-800"
      abierta={abierta}
      onToggle={() => setAbierta((v) => !v)}
      resumen={`${anio}: ${pagadosAnio.length}/12 pagados · ${formatMoney(totalAnio)} · Valor pactado ${formatMoney(valorPactado)}`}
    >
      <div className="flex items-center justify-between px-4 py-2 bg-slate-50/60">
        <button
          type="button"
          onClick={() => setAnio((a) => a - 1)}
          className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-white"
          title="Año anterior"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <span className="text-xs font-bold text-slate-600">{anio}</span>
        <button
          type="button"
          onClick={() => setAnio((a) => a + 1)}
          className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-white"
          title="Año siguiente"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>

      <ul className="divide-y divide-slate-100">
        {MESES.map((nombre, i) => {
          const periodo = periodoDe(anio, i);
          const pagado = porPeriodo[periodo];
          const datos = borrador(periodo);
          const ocupado = guardando === periodo;
          return (
            <li
              key={periodo}
              onClick={(e) => !pagado && !esCampo(e) && registrar(i)}
              title={pagado ? "Aporte registrado" : "Toca la línea para registrar el pago"}
              className={`group flex items-start gap-3 px-4 py-2.5 text-xs transition-colors ${
                pagado ? "bg-emerald-50/30" : "cursor-pointer hover:bg-slate-50"
              } ${ocupado ? "opacity-60 pointer-events-none" : ""}`}
            >
              <Circulo pagado={!!pagado} ocupado={ocupado} />
              <div className="flex-1 min-w-0 flex flex-wrap items-center gap-x-4 gap-y-1">
                <span className={`w-20 font-semibold ${pagado ? "text-slate-400 line-through decoration-emerald-400" : "text-slate-800"}`}>
                  {nombre}
                </span>
                {pagado ? (
                  <>
                    <span className="font-bold text-slate-600">{formatMoney(pagado.monto)}</span>
                    <span className="text-slate-400">{formatDate(pagado.fecha)}</span>
                  </>
                ) : (
                  <>
                    <label className="flex items-center gap-1 text-slate-400">
                      $
                      <MoneyInput
                        value={datos.monto}
                        onChange={(e) => editar(periodo, "monto", e.target.value)}
                        aria-label={`Valor del aporte de ${nombre}`}
                        className={`${inputClase} w-24 font-bold`}
                      />
                    </label>
                    <input
                      type="date"
                      max={hoy}
                      value={datos.fecha}
                      onChange={(e) => editar(periodo, "fecha", e.target.value)}
                      aria-label={`Fecha del aporte de ${nombre}`}
                      className={`${inputClase} w-32`}
                    />
                  </>
                )}
              </div>
              <Estado pagado={!!pagado} />
            </li>
          );
        })}
      </ul>

      {sinMes.cantidad > 0 && (
        <p className="px-4 py-2.5 text-[11px] text-slate-500 bg-slate-50/60 border-t border-slate-100">
          Además hay {sinMes.cantidad} aporte{sinMes.cantidad === 1 ? "" : "s"} de {anio} registrado
          {sinMes.cantidad === 1 ? "" : "s"} sin mes asignado ({formatMoney(sinMes.total)}). Revísalos en el historial
          antes de marcar meses para no cobrar dos veces.
        </p>
      )}
    </Seccion>
  );
};

export const MultasSocio = ({ socio, onRegistrado }) => {
  const [abierta, setAbierta] = useState(false);
  const [borradores, setBorradores] = useState({});
  const [guardando, setGuardando] = useState(null);

  const hoy = fechaLocalISO();
  const multas = useMemo(
    () =>
      (socio.multas || [])
        .slice()
        .sort((a, b) => Number(a.pagada) - Number(b.pagada) || new Date(b.fecha) - new Date(a.fecha)),
    [socio.multas]
  );
  const pendientes = multas.filter((m) => !m.pagada);

  const borrador = (multa) => ({
    concepto: textoPlano(multa.descripcion),
    monto: multa.monto,
    fecha: hoy,
    ...borradores[multa.id],
  });
  const editar = (multa, campo, valor) =>
    setBorradores((prev) => ({ ...prev, [multa.id]: { ...borrador(multa), ...prev[multa.id], [campo]: valor } }));

  const pagar = async (multa) => {
    if (multa.pagada || guardando) return;
    const { concepto, monto, fecha } = borrador(multa);
    const conceptoFinal = concepto.trim() || "Multa";
    if (!montoValido(monto)) return alert("Escribe un valor mayor a cero para la multa.");
    if (!fecha || fecha > hoy) return alert("La fecha del pago no puede estar vacía ni ser futura.");
    if (!window.confirm(`¿Registrar el pago de la multa "${conceptoFinal}" por ${formatMoney(monto)} con fecha ${formatDate(fecha)}?`)) return;

    const cambioConcepto = concepto.trim() && concepto.trim() !== textoPlano(multa.descripcion).trim();
    const cambioMonto = Number(monto) !== Number(multa.monto);
    try {
      setGuardando(multa.id);
      // Si se modificó la multa, se actualiza primero para que el pago la salde exactamente.
      if (cambioConcepto || cambioMonto) {
        await api.put(`/socios/${socio.id}/multas/${multa.id}`, {
          ...(cambioConcepto ? { descripcion: concepto.trim() } : {}),
          ...(cambioMonto ? { monto } : {}),
        });
      }
      await api.post(`/socios/${socio.id}/movimientos`, {
        tipo_movimiento: "PAGO_MULTA",
        monto,
        fecha,
        multa_id: multa.id,
        descripcion: `Pago de multa: ${conceptoFinal}`.slice(0, 255),
      });
      setBorradores((prev) => {
        const { [multa.id]: _omitido, ...resto } = prev;
        return resto;
      });
      await onRegistrado();
    } catch (err) {
      console.error(err);
      alert(mensajeError(err, "Error al registrar el pago de la multa."));
      await onRegistrado();
    } finally {
      setGuardando(null);
    }
  };

  const totalPendiente = pendientes.reduce((suma, m) => suma + Number(m.monto), 0);

  return (
    <Seccion
      titulo="Multas"
      acento="text-rose-800"
      abierta={abierta}
      onToggle={() => setAbierta((v) => !v)}
      resumen={
        multas.length === 0
          ? "Sin multas"
          : `${pendientes.length} pendiente${pendientes.length === 1 ? "" : "s"} · ${formatMoney(totalPendiente)} · ${multas.length - pendientes.length} pagada${multas.length - pendientes.length === 1 ? "" : "s"}`
      }
    >
      {multas.length === 0 ? (
        <p className="px-4 py-5 text-center text-xs text-slate-400">Este socio no tiene multas cargadas</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {multas.map((multa) => {
            const datos = borrador(multa);
            const ocupado = guardando === multa.id;
            return (
              <li
                key={multa.id}
                onClick={(e) => !multa.pagada && !esCampo(e) && pagar(multa)}
                title={multa.pagada ? "Multa pagada" : "Toca la línea para registrar el pago"}
                className={`group flex items-start gap-3 px-4 py-2.5 text-xs transition-colors ${
                  multa.pagada ? "bg-emerald-50/30" : "cursor-pointer hover:bg-slate-50"
                } ${ocupado ? "opacity-60 pointer-events-none" : ""}`}
              >
                <Circulo pagado={multa.pagada} ocupado={ocupado} />
                <div className="flex-1 min-w-0 space-y-1">
                  {multa.pagada ? (
                    <>
                      <RichTextDisplay
                        value={multa.descripcion || "Multa"}
                        className="font-semibold text-slate-400 line-through decoration-emerald-400"
                      />
                      <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-slate-400">
                        <span className="font-bold text-slate-600">{formatMoney(multa.monto)}</span>
                        <span>Cargada {formatDate(multa.fecha)}</span>
                        <span>{multa.fecha_pago ? `Pagada ${formatDate(multa.fecha_pago)}` : "Pagada (registro anterior)"}</span>
                      </div>
                    </>
                  ) : (
                    <>
                      <input
                        type="text"
                        maxLength={240}
                        value={datos.concepto}
                        onChange={(e) => editar(multa, "concepto", e.target.value)}
                        placeholder="Concepto de la multa"
                        aria-label="Concepto de la multa"
                        className={`${inputClase} w-full font-semibold text-slate-800`}
                      />
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-slate-400">
                        <label className="flex items-center gap-1">
                          $
                          <MoneyInput
                            value={datos.monto}
                            onChange={(e) => editar(multa, "monto", e.target.value)}
                            aria-label="Valor de la multa"
                            className={`${inputClase} w-24 font-bold`}
                          />
                        </label>
                        <label className="flex items-center gap-1">
                          Pago
                          <input
                            type="date"
                            max={hoy}
                            value={datos.fecha}
                            onChange={(e) => editar(multa, "fecha", e.target.value)}
                            aria-label="Fecha del pago de la multa"
                            className={`${inputClase} w-32`}
                          />
                        </label>
                        <span>Cargada {formatDate(multa.fecha)}</span>
                      </div>
                    </>
                  )}
                </div>
                <Estado pagado={multa.pagada} />
              </li>
            );
          })}
        </ul>
      )}
    </Seccion>
  );
};

const ESTADO_PRESTAMO = {
  PAGADO: { texto: "Pagado", clase: "bg-emerald-50 text-emerald-700" },
  EN_MORA: { texto: "En mora", clase: "bg-rose-50 text-rose-700" },
  PENDIENTE: { texto: "Al día", clase: "bg-amber-50 text-amber-700" },
};

export const DeudasCredito = ({ socio }) => {
  const [abierta, setAbierta] = useState(false);
  const navigate = useNavigate();
  const prestamos = useMemo(
    () =>
      (socio.prestamos || [])
        .slice()
        .sort((a, b) => Number(a.estado === "PAGADO") - Number(b.estado === "PAGADO") || b.id - a.id),
    [socio.prestamos]
  );
  const vigentes = prestamos.filter((p) => p.estado !== "PAGADO");

  return (
    <Seccion
      titulo="Deudas de crédito"
      acento="text-purple-800"
      abierta={abierta}
      onToggle={() => setAbierta((v) => !v)}
      resumen={
        prestamos.length === 0
          ? "Sin préstamos"
          : `${vigentes.length} vigente${vigentes.length === 1 ? "" : "s"} · Saldo ${formatMoney(socio.saldo_prestamos_pendiente)}`
      }
    >
      {prestamos.length === 0 ? (
        <p className="px-4 py-5 text-center text-xs text-slate-400">Este socio no tiene préstamos registrados</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {prestamos.map((p) => {
            const pagado = p.estado === "PAGADO";
            const estado = ESTADO_PRESTAMO[p.estado] || { texto: p.estado, clase: "bg-slate-100 text-slate-600" };
            return (
              <li
                key={p.id}
                onClick={() => navigate(`/prestamos?prestamo=${p.id}`)}
                title="Ver este préstamo en el apartado de Préstamos"
                className={`group flex items-start gap-3 px-4 py-2.5 text-xs cursor-pointer transition-colors ${
                  pagado ? "bg-emerald-50/30 hover:bg-emerald-50/60" : "hover:bg-slate-50"
                }`}
              >
                <Circulo pagado={pagado} />
                <div className="flex-1 min-w-0 flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span className={`font-semibold ${pagado ? "text-slate-400 line-through decoration-emerald-400" : "text-slate-800"}`}>
                    Préstamo #{p.id}
                  </span>
                  <span className="font-bold text-slate-600">Saldo {formatMoney(p.saldo_pendiente)}</span>
                  <span className="text-slate-400">
                    {formatMoney(p.monto_prestado)} · Cuotas {p.cuotas_pagadas}/{p.numero_cuotas}
                  </span>
                </div>
                <span className={`shrink-0 px-2 py-0.5 rounded-full text-[10px] font-bold ${estado.clase}`}>{estado.texto}</span>
                <ChevronRight className="w-4 h-4 shrink-0 text-slate-300 group-hover:text-purple-500" />
              </li>
            );
          })}
        </ul>
      )}
    </Seccion>
  );
};
