import React, { useMemo, useState } from "react";
import { Check, ChevronDown, ChevronLeft, ChevronRight, Plus, Trash2 } from "lucide-react";
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

// Actividades del socio: una línea por actividad. Se elige el tipo:
// - "Rifa interna": se indica el mes; en la impresión va al lado de la cuota de ese mes.
//   La ganancia se escribe a mano (funcionamiento de siempre).
// - "Otra": se escribe el nombre; en la impresión va en la columna Actividad. Aparece
//   "Valor por unidad": si se llena, Ganancia = valor por unidad x cantidad vendida
//   (el servidor vuelve a calcularla al guardar). Si se deja vacío, la ganancia se
//   escribe a mano como antes (así se conservan las líneas anteriores).
const TIPOS_ACTIVIDAD = { RIFA_INTERNA: "Rifa interna", OTRA: "Otra" };

const lineaDesde = (a) => ({
  clave: `id-${a.id}`,
  id: a.id,
  tipo: a.tipo || "OTRA",
  nombre: a.tipo === "RIFA_INTERNA" ? "" : a.nombre,
  mes: a.mes == null ? "" : String(a.mes),
  cantidad: a.cantidad_vendida == null ? "" : String(a.cantidad_vendida),
  valorUnidad: a.valor_unidad == null ? "" : String(a.valor_unidad),
  ganancia: String(a.ganancia ?? ""),
});

const usaValorUnidad = (l) => l.tipo === "OTRA" && l.valorUnidad !== "" && l.valorUnidad != null;
// Ganancia calculada: valor por unidad x cantidad vendida, redondeada a centavos.
const gananciaCalculada = (l) => {
  if (!usaValorUnidad(l) || l.cantidad === "") return "";
  return String(Math.round(Number(l.valorUnidad) * Number(l.cantidad) * 100) / 100);
};
// Ganancia que se muestra y se guarda: la calculada si hay valor por unidad.
const gananciaDe = (l) => (usaValorUnidad(l) ? gananciaCalculada(l) : l.ganancia);

const etiquetaActividad = (l) =>
  l.tipo === "RIFA_INTERNA" ? `Rifa interna${l.mes ? ` de ${MESES[Number(l.mes) - 1]}` : ""}` : l.nombre || "Actividad";

let secuenciaActividad = 0;

export const ActividadesSocio = ({ socio, onRegistrado }) => {
  const [abierta, setAbierta] = useState(false);
  const [borradores, setBorradores] = useState({});
  const [nuevas, setNuevas] = useState([]);
  const [guardando, setGuardando] = useState(null);

  const guardadas = useMemo(() => (socio.actividades || []).map(lineaDesde), [socio.actividades]);
  const lineas = [...guardadas.map((l) => ({ ...l, ...borradores[l.clave] })), ...nuevas];
  const total = guardadas.reduce((suma, l) => suma + Number(l.ganancia || 0), 0);
  const original = (clave) => guardadas.find((l) => l.clave === clave);
  const sucia = (l) => {
    if (l.id == null) return true;
    const o = original(l.clave);
    return !o || o.tipo !== l.tipo || o.nombre !== l.nombre || o.mes !== l.mes
      || o.cantidad !== l.cantidad || (o.tipo === "OTRA" ? o.valorUnidad : "") !== (l.tipo === "OTRA" ? l.valorUnidad : "")
      || Number(o.ganancia) !== Number(gananciaDe(l));
  };

  const editar = (l, campo, valor) => {
    // Con valor por unidad, la ganancia se recalcula al cambiar el valor o la cantidad.
    const siguiente = { ...l, [campo]: valor };
    const cambios = { [campo]: valor };
    if (usaValorUnidad(siguiente) && siguiente.cantidad !== "") cambios.ganancia = gananciaCalculada(siguiente);
    if (l.id == null) {
      setNuevas((ns) => ns.map((n) => (n.clave === l.clave ? { ...n, ...cambios } : n)));
    } else {
      setBorradores((prev) => ({ ...prev, [l.clave]: { ...prev[l.clave], ...cambios } }));
    }
  };

  const agregar = () => {
    setAbierta(true);
    setNuevas((ns) => [
      ...ns,
      { clave: `nueva-${++secuenciaActividad}`, id: null, tipo: "", nombre: "", mes: "", cantidad: "", valorUnidad: "", ganancia: "" },
    ]);
  };

  const quitarBorrador = (l) => {
    if (l.id == null) setNuevas((ns) => ns.filter((n) => n.clave !== l.clave));
    else setBorradores(({ [l.clave]: _omitido, ...resto }) => resto);
  };

  const guardar = async (l) => {
    if (guardando) return;
    if (!l.tipo) return alert("Elige el tipo de actividad: Rifa interna u Otra.");
    if (l.tipo === "RIFA_INTERNA" && !l.mes) return alert("Elige el mes de la rifa interna.");
    if (l.tipo === "OTRA" && !l.nombre.trim()) return alert("Escribe el nombre de la actividad.");
    if (l.cantidad !== "" && !/^\d+$/.test(String(l.cantidad).trim())) return alert("La cantidad vendida debe ser un número entero.");
    const conValor = usaValorUnidad(l);
    if (conValor && !(Number(l.valorUnidad) >= 0)) return alert("El valor por unidad debe ser un número mayor o igual a cero.");
    if (conValor && l.cantidad === "") return alert("Escribe la cantidad vendida para calcular la ganancia.");
    const ganancia = gananciaDe(l);
    if (ganancia === "" || !(Number(ganancia) >= 0)) return alert("Escribe la ganancia (puede ser 0).");
    const datos = {
      tipo: l.tipo,
      nombre: l.tipo === "OTRA" ? l.nombre.trim() : null,
      mes: l.tipo === "RIFA_INTERNA" ? Number(l.mes) : null,
      cantidad_vendida: l.cantidad === "" ? null : Number(l.cantidad),
      valor_unidad: conValor ? Number(l.valorUnidad).toFixed(2) : null,
      ganancia: Number(ganancia).toFixed(2),
    };
    try {
      setGuardando(l.clave);
      if (l.id == null) await api.post(`/socios/${socio.id}/actividades`, datos);
      else await api.put(`/socios/${socio.id}/actividades/${l.id}`, datos);
      quitarBorrador(l);
      await onRegistrado();
    } catch (err) {
      console.error(err);
      alert(mensajeError(err, "No se pudo guardar la actividad."));
    } finally {
      setGuardando(null);
    }
  };

  const eliminar = async (l) => {
    if (l.id == null) return quitarBorrador(l);
    const o = original(l.clave);
    if (!window.confirm(`¿Eliminar "${etiquetaActividad(o)}" (${formatMoney(o.ganancia)})?`)) return;
    try {
      setGuardando(l.clave);
      await api.delete(`/socios/${socio.id}/actividades/${l.id}`);
      quitarBorrador(l);
      await onRegistrado();
    } catch (err) {
      console.error(err);
      alert(mensajeError(err, "No se pudo eliminar la actividad."));
    } finally {
      setGuardando(null);
    }
  };

  return (
    <Seccion
      titulo="Actividades"
      acento="text-sky-800"
      abierta={abierta}
      onToggle={() => setAbierta((v) => !v)}
      resumen={
        guardadas.length === 0
          ? "Sin actividades registradas"
          : `${guardadas.length} actividad${guardadas.length === 1 ? "" : "es"} · Ganancia ${formatMoney(total)}`
      }
    >
      {lineas.length === 0 ? (
        <p className="px-4 py-5 text-center text-xs text-slate-400">Este socio aún no tiene actividades registradas</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          <li className="hidden sm:grid grid-cols-[minmax(0,1fr)_100px_80px_110px_64px] gap-3 px-4 py-2 text-[10px] font-bold text-slate-400 uppercase tracking-wider bg-slate-50/60">
            <span>Actividad</span>
            <span className="text-right">Valor por unidad</span>
            <span className="text-right">Cant. vendida</span>
            <span className="text-right">Ganancia</span>
            <span />
          </li>
          {lineas.map((l) => {
            const pendiente = sucia(l);
            const ocupado = guardando === l.clave;
            const enter = (e) => { if (e.key === "Enter") { e.preventDefault(); guardar(l); } };
            return (
              <li
                key={l.clave}
                className={`grid grid-cols-[minmax(0,1fr)_64px] sm:grid-cols-[minmax(0,1fr)_100px_80px_110px_64px] gap-x-3 gap-y-1 items-center px-4 py-2.5 text-xs ${
                  pendiente ? "bg-amber-50" : ""
                } ${ocupado ? "opacity-60 pointer-events-none" : ""}`}
              >
                <div className="flex flex-wrap items-center gap-2 min-w-0">
                  <select
                    value={l.tipo}
                    onChange={(e) => editar(l, "tipo", e.target.value)}
                    aria-label="Tipo de actividad"
                    className={`${inputClase} w-28 font-semibold text-slate-700`}
                  >
                    <option value="" disabled>Elegir tipo...</option>
                    {Object.entries(TIPOS_ACTIVIDAD).map(([valor, texto]) => (
                      <option key={valor} value={valor}>{texto}</option>
                    ))}
                  </select>
                  {l.tipo === "OTRA" && (
                    <input
                      type="text"
                      maxLength={150}
                      value={l.nombre}
                      onChange={(e) => editar(l, "nombre", e.target.value)}
                      onKeyDown={enter}
                      placeholder="Nombre de la actividad"
                      aria-label="Nombre de la actividad"
                      className={`${inputClase} flex-1 min-w-[8rem] font-semibold text-slate-800`}
                    />
                  )}
                  {l.tipo === "RIFA_INTERNA" && (
                    <select
                      value={l.mes}
                      onChange={(e) => editar(l, "mes", e.target.value)}
                      aria-label="Mes de la rifa interna"
                      className={`${inputClase} w-28 text-slate-700`}
                    >
                      <option value="" disabled>¿Qué mes?</option>
                      {MESES.map((nombre, i) => (
                        <option key={nombre} value={String(i + 1)}>{nombre}</option>
                      ))}
                    </select>
                  )}
                </div>
                <div className="flex items-center justify-end gap-1 sm:order-last">
                  {pendiente && (
                    <button type="button" onClick={() => guardar(l)} title="Guardar línea" aria-label="Guardar línea"
                      className="p-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white">
                      <Check className="w-3.5 h-3.5" />
                    </button>
                  )}
                  <button type="button" onClick={() => eliminar(l)} title="Eliminar línea" aria-label="Eliminar línea"
                    className="p-1.5 rounded-lg text-rose-500 hover:text-rose-700 hover:bg-rose-50">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
                {l.tipo === "RIFA_INTERNA" || !l.tipo ? (
                  <span className="hidden sm:block" />
                ) : (
                  <label className="flex items-center gap-1 text-slate-400 sm:justify-end" title="Valor de cada unidad vendida. Ganancia = valor por unidad × cantidad vendida">
                    <span className="sm:hidden">Valor por unidad</span>
                    $
                    <MoneyInput
                      value={l.valorUnidad}
                      onChange={(e) => editar(l, "valorUnidad", e.target.value)}
                      onKeyDown={enter}
                      placeholder="Opcional"
                      aria-label="Valor por unidad"
                      className={`${inputClase} w-20 text-right`}
                    />
                  </label>
                )}
                <label className="flex items-center gap-1 text-slate-400 sm:justify-end">
                  <span className="sm:hidden">Cant.</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={l.cantidad}
                    onChange={(e) => editar(l, "cantidad", e.target.value.replace(/\D/g, ""))}
                    onKeyDown={enter}
                    placeholder={usaValorUnidad(l) ? "Requerida" : "Opcional"}
                    aria-label={usaValorUnidad(l) ? "Cantidad vendida" : "Cantidad vendida (opcional)"}
                    className={`${inputClase} w-16 text-right`}
                  />
                </label>
                <label
                  className="flex items-center gap-1 text-slate-400 sm:justify-end"
                  title={usaValorUnidad(l) ? "Calculada: valor por unidad × cantidad vendida" : undefined}
                >
                  $
                  <MoneyInput
                    value={gananciaDe(l)}
                    onChange={(e) => editar(l, "ganancia", e.target.value)}
                    onKeyDown={enter}
                    readOnly={usaValorUnidad(l)}
                    placeholder={usaValorUnidad(l) ? "Falta cantidad" : "0"}
                    aria-label={usaValorUnidad(l) ? "Ganancia (calculada)" : "Ganancia"}
                    className={`${inputClase} w-24 text-right font-bold ${usaValorUnidad(l) ? "text-sky-700 border-solid cursor-default" : ""}`}
                  />
                </label>
              </li>
            );
          })}
        </ul>
      )}
      <div className="px-4 py-3 border-t border-slate-100">
        <button
          type="button"
          onClick={agregar}
          className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 border-2 border-dashed border-sky-200 rounded-xl text-xs font-black text-sky-700 hover:bg-sky-50 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" /> Agregar actividad
        </button>
        {lineas.some(sucia) && (
          <p className="mt-2 text-[11px] text-amber-700">Hay líneas sin guardar: presiona ✓ o Enter para guardarlas.</p>
        )}
      </div>
    </Seccion>
  );
};

const ordinal = (orden) => (orden === 2 ? "segundo préstamo" : orden >= 3 ? `préstamo #${orden} del socio` : null);

// Todas las obligaciones pendientes del socio (préstamos, intereses y multas), calculadas en el servidor.
export const DeduccionesSocio = ({ socio }) => {
  const [abierta, setAbierta] = useState(false);
  const navigate = useNavigate();
  const d = socio.deducciones || {};
  const prestamos = d.prestamos || [];
  const multas = d.multas || [];
  const sinDeudas = prestamos.length === 0 && multas.length === 0;

  return (
    <Seccion
      titulo="Deducciones"
      acento="text-amber-800"
      abierta={abierta}
      onToggle={() => setAbierta((v) => !v)}
      resumen={sinDeudas ? "Sin deudas pendientes" : `Total que debe: ${formatMoney(d.total_deducciones)}`}
    >
      {sinDeudas ? (
        <p className="px-4 py-5 text-center text-xs text-slate-400">Este socio no tiene deudas pendientes</p>
      ) : (
        <>
          <ul className="divide-y divide-slate-100">
            {prestamos.map((p) => (
              <li
                key={`p-${p.prestamo_id}`}
                onClick={() => navigate(`/prestamos?prestamo=${p.prestamo_id}`)}
                title="Ver este préstamo en el apartado de Préstamos"
                className="group flex items-start gap-3 px-4 py-2.5 text-xs cursor-pointer hover:bg-slate-50 transition-colors"
              >
                <div className="flex-1 min-w-0 flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span className="font-semibold text-slate-800">
                    Préstamo #{p.prestamo_id}
                    {ordinal(p.orden_socio) && <span className="font-normal text-slate-400"> ({ordinal(p.orden_socio)})</span>}
                  </span>
                  <span className="text-slate-500">Capital {formatMoney(p.capital_pendiente)}</span>
                  <span className="text-slate-500">Intereses vencidos {formatMoney(p.intereses_pendientes)}</span>
                </div>
                <span className="shrink-0 font-bold text-slate-700">{formatMoney(p.total)}</span>
                <ChevronRight className="w-4 h-4 shrink-0 text-slate-300 group-hover:text-amber-500" />
              </li>
            ))}
            {multas.map((m) => (
              <li key={`m-${m.multa_id}`} className="flex items-start gap-3 px-4 py-2.5 text-xs">
                <div className="flex-1 min-w-0 flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span className="font-semibold text-slate-800">Multa</span>
                  <RichTextDisplay value={m.descripcion || "Multa"} className="text-slate-500" />
                  <span className="text-slate-400">Cargada {formatDate(m.fecha)}</span>
                </div>
                <span className="shrink-0 font-bold text-slate-700">{formatMoney(m.monto)}</span>
              </li>
            ))}
          </ul>
          <dl className="px-4 py-3 bg-amber-50 border-t border-amber-100 text-xs space-y-1">
            <div className="flex justify-between"><dt className="text-slate-500">Capital de préstamos pendiente</dt><dd className="font-semibold">{formatMoney(d.total_capital_pendiente)}</dd></div>
            <div className="flex justify-between"><dt className="text-slate-500">Intereses pendientes (cuotas vencidas)</dt><dd className="font-semibold">{formatMoney(d.total_intereses_pendientes)}</dd></div>
            <div className="flex justify-between"><dt className="text-slate-500">Multas pendientes</dt><dd className="font-semibold">{formatMoney(d.total_multas_pendientes)}</dd></div>
            <div className="flex justify-between border-t border-amber-100 pt-1"><dt className="font-bold text-amber-800">Total que debe</dt><dd className="font-black text-amber-800">{formatMoney(d.total_deducciones)}</dd></div>
          </dl>
        </>
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
