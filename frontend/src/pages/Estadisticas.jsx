import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  ChartColumn, ChevronDown, Filter, Save, Trash2, Eye, AlertTriangle, ArrowLeft, Table2, TrendingUp, TrendingDown, Scale, Hash,
} from "lucide-react";
import api from "../api/client";
import { useAuth } from "../context/AuthContext";
import { formatMoney, formatDate } from "../utils/formatters";

// Estadísticas de los movimientos económicos del año consultado.
// Las cifras vienen del backend (datos reales); una estadística guardada es una
// fotografía: se muestra tal como quedó al guardarla.

const NATURALEZAS = {
  INGRESO: { etiqueta: "Ingresos", color: "var(--serie-ingreso)", clave: "ingresos" },
  EGRESO: { etiqueta: "Egresos", color: "var(--serie-egreso)", clave: "egresos" },
  OTRO: { etiqueta: "Otros (multas impuestas)", color: "var(--serie-otro)", clave: "otros" },
};
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const compacto = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", notation: "compact", maximumFractionDigits: 1 });

const ultimoDiaMes = (mes) => {
  const [a, m] = mes.split("-").map(Number);
  return `${mes}-${String(new Date(a, m, 0).getDate()).padStart(2, "0")}`;
};

const etiquetaPeriodo = (clave, granularidad, corta = false) => {
  const [a, m, d] = clave.split("-");
  if (granularidad === "dia") return `${Number(d)} ${MESES[Number(m) - 1]}`;
  return corta ? MESES[Number(m) - 1] : `${MESES[Number(m) - 1]} ${a}`;
};

const describirFiltros = (filtros, opciones) => {
  const partes = [];
  if (filtros.modo === "meses" && filtros.fecha_desde) {
    const d = filtros.fecha_desde.slice(0, 7), h = (filtros.fecha_hasta || filtros.fecha_desde).slice(0, 7);
    partes.push(d === h ? etiquetaPeriodo(d, "mes") : `${etiquetaPeriodo(d, "mes")} a ${etiquetaPeriodo(h, "mes")}`);
  } else if (filtros.fecha_desde || filtros.fecha_hasta) {
    partes.push(`${filtros.fecha_desde ? formatDate(filtros.fecha_desde) : "inicio"} a ${filtros.fecha_hasta ? formatDate(filtros.fecha_hasta) : "hoy"}`);
  } else {
    partes.push("Todo el año");
  }
  if (filtros.evento) {
    const ev = opciones?.eventos?.find((e) => e.clave === filtros.evento);
    partes.push(ev ? `${ev.categoria}: ${ev.nombre}` : "Un evento");
  }
  if (filtros.tipos?.length) {
    partes.push(filtros.tipos.length === 1
      ? (opciones?.tipos?.find((t) => t.tipo === filtros.tipos[0])?.etiqueta || filtros.tipos[0])
      : `${filtros.tipos.length} tipos de movimiento`);
  }
  return partes.join(" · ");
};

// Ancho disponible de un contenedor (para dibujar las gráficas a su medida).
const useAncho = () => {
  const ref = useRef(null);
  const [ancho, setAncho] = useState(0);
  useLayoutEffect(() => {
    if (!ref.current) return undefined;
    const obs = new ResizeObserver(([entrada]) => setAncho(entrada.contentRect.width));
    obs.observe(ref.current);
    return () => obs.disconnect();
  }, []);
  return [ref, ancho];
};

const pasoBonito = (max, divisiones = 4) => {
  if (max <= 0) return 1;
  const bruto = max / divisiones;
  const potencia = 10 ** Math.floor(Math.log10(bruto));
  const n = bruto / potencia;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * potencia;
};

// Barra con las esquinas superiores redondeadas (4px), apoyada en la línea base.
const barraPath = (x, y, w, h) => {
  const r = Math.min(4, w / 2, h);
  return `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`;
};

const Leyenda = ({ series }) => (
  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
    {series.map((s) => (
      <span key={s.etiqueta} className="inline-flex items-center gap-1.5">
        <span className="w-3 h-3 rounded-sm" style={{ background: s.color }} />
        {s.etiqueta}
      </span>
    ))}
  </div>
);

// Evolución en el tiempo: barras agrupadas de ingresos y egresos por mes o día.
const GraficaEvolucion = ({ serie, granularidad }) => {
  const [ref, anchoCont] = useAncho();
  const [activo, setActivo] = useState(null);
  const alto = 260, margen = { izq: 64, der: 12, arriba: 12, abajo: 30 };
  const minPorGrupo = granularidad === "dia" ? 16 : 36;
  const ancho = Math.max(anchoCont, margen.izq + margen.der + serie.length * minPorGrupo);
  const internoW = ancho - margen.izq - margen.der, internoH = alto - margen.arriba - margen.abajo;
  const max = Math.max(0, ...serie.map((p) => Math.max(p.ingresos, p.egresos)));
  const paso = pasoBonito(max);
  const tope = Math.max(paso, Math.ceil(max / paso) * paso);
  const ticks = Array.from({ length: Math.round(tope / paso) + 1 }, (_, i) => i * paso);
  const grupoW = internoW / Math.max(1, serie.length);
  const barraW = Math.max(3, Math.min(28, (grupoW - 6) / 2 - 1));
  const y = (v) => margen.arriba + internoH - (v / tope) * internoH;
  const cadaEtiqueta = Math.max(1, Math.ceil(serie.length / Math.max(1, Math.floor(internoW / 56))));

  return (
    <div className="viz-root relative">
      <div ref={ref} className="overflow-x-auto">
        {anchoCont > 0 && (
          <svg width={ancho} height={alto} role="img" aria-label="Ingresos y egresos por periodo" onMouseLeave={() => setActivo(null)}>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={margen.izq} x2={ancho - margen.der} y1={y(t)} y2={y(t)} stroke="var(--viz-grid)" strokeWidth="1" />
                <text x={margen.izq - 8} y={y(t)} dy="0.32em" textAnchor="end" fontSize="11" fill="var(--viz-eje)">{compacto.format(t)}</text>
              </g>
            ))}
            {serie.map((p, i) => {
              const x0 = margen.izq + i * grupoW;
              const centro = x0 + grupoW / 2;
              return (
                <g key={p.periodo}>
                  {activo === i && <rect x={x0} y={margen.arriba} width={grupoW} height={internoH} fill="var(--viz-grid)" opacity="0.45" />}
                  {[["ingresos", "var(--serie-ingreso)", -1], ["egresos", "var(--serie-egreso)", 1]].map(([k, color, lado]) => {
                    const h = (p[k] / tope) * internoH;
                    if (h <= 0) return null;
                    const x = lado < 0 ? centro - 1 - barraW : centro + 1;
                    return <path key={k} d={barraPath(x, y(p[k]), barraW, h)} fill={color} />;
                  })}
                  {i % cadaEtiqueta === 0 && (
                    <text x={centro} y={alto - 10} textAnchor="middle" fontSize="11" fill="var(--viz-eje)">
                      {etiquetaPeriodo(p.periodo, granularidad, serie.length > 12)}
                    </text>
                  )}
                  <rect x={x0} y={margen.arriba} width={grupoW} height={internoH} fill="transparent"
                        onMouseEnter={() => setActivo(i)} onFocus={() => setActivo(i)} tabIndex={0}
                        aria-label={`${etiquetaPeriodo(p.periodo, granularidad)}: ingresos ${formatMoney(p.ingresos)}, egresos ${formatMoney(p.egresos)}`} />
                </g>
              );
            })}
            <line x1={margen.izq} x2={ancho - margen.der} y1={y(0)} y2={y(0)} stroke="var(--viz-eje)" strokeWidth="1" />
          </svg>
        )}
      </div>
      {activo !== null && serie[activo] && (
        <div
          className="pointer-events-none absolute top-2 z-10 min-w-44 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg"
          style={{ left: Math.min(Math.max(0, margen.izq + activo * grupoW + grupoW / 2 - 90), Math.max(0, anchoCont - 190)) }}
        >
          <p className="font-bold text-slate-800 mb-1">{etiquetaPeriodo(serie[activo].periodo, granularidad)}</p>
          {[["Ingresos", "ingresos", "var(--serie-ingreso)"], ["Egresos", "egresos", "var(--serie-egreso)"]].map(([e, k, c]) => (
            <p key={k} className="flex items-center justify-between gap-4 text-slate-600">
              <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: c }} />{e}</span>
              <span className="font-semibold text-slate-800">{formatMoney(serie[activo][k])}</span>
            </p>
          ))}
          <p className="flex justify-between gap-4 border-t border-slate-100 mt-1 pt-1 text-slate-600">
            <span>Balance</span><span className="font-bold text-slate-800">{formatMoney(serie[activo].balance)}</span>
          </p>
        </div>
      )}
    </div>
  );
};

// Distribución por tipo de movimiento: barras horizontales con su valor escrito.
const GraficaPorTipo = ({ porTipo }) => {
  const max = Math.max(1, ...porTipo.map((t) => t.total));
  return (
    <ul className="viz-root space-y-2.5">
      {porTipo.map((t) => (
        <li key={t.tipo} title={`${t.etiqueta}: ${formatMoney(t.total)} en ${t.cantidad} registro(s)`}>
          <div className="flex items-baseline justify-between gap-3 text-xs">
            <span className="font-semibold text-slate-700 truncate">
              {t.etiqueta}
              {t.origen && <span className="font-normal text-slate-400"> · {t.origen}</span>}
            </span>
            <span className="shrink-0 text-slate-500"><strong className="text-slate-800">{formatMoney(t.total)}</strong> · {t.cantidad}</span>
          </div>
          <div className="mt-1 h-2.5 rounded-full bg-slate-100 overflow-hidden">
            <div className="h-full rounded-full" style={{ width: `${Math.max(1, (t.total / max) * 100)}%`, background: NATURALEZAS[t.naturaleza].color }} />
          </div>
        </li>
      ))}
    </ul>
  );
};

// Detalle de un periodo: cada movimiento con su concepto, origen y descripción.
const DetallePeriodo = ({ movimientos }) => (
  <div className="rounded-xl border border-slate-100 bg-slate-50/60 overflow-x-auto">
    <table className="w-full text-xs">
      <thead><tr className="text-left text-[10px] uppercase tracking-wider text-slate-400 border-b border-slate-100">
        <th className="py-1.5 px-2">Fecha</th><th className="py-1.5 px-2">Concepto</th>
        <th className="py-1.5 px-2">Descripción</th><th className="py-1.5 px-2 text-right">Valor</th>
      </tr></thead>
      <tbody>
        {movimientos.map((m) => (
          <tr key={`${m.tipo}-${m.referencia}`} className="border-b border-slate-100/70 last:border-0 text-slate-700 align-top">
            <td className="py-1.5 px-2 whitespace-nowrap text-slate-500">{formatDate(m.fecha)}</td>
            <td className="py-1.5 px-2">
              <span className="inline-flex items-center gap-1.5 font-semibold">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: NATURALEZAS[m.naturaleza]?.color }} />
                {m.concepto}
              </span>
              {m.origen && <p className="text-[10px] text-slate-400 pl-3.5">{m.origen}</p>}
            </td>
            <td className="py-1.5 px-2"><div className="max-w-[18rem] lg:max-w-[24rem]">{m.descripcion}</div></td>
            <td className={`py-1.5 px-2 text-right font-bold whitespace-nowrap ${m.naturaleza === "EGRESO" ? "text-rose-700" : m.naturaleza === "INGRESO" ? "text-emerald-700" : "text-slate-600"}`}>
              {m.naturaleza === "EGRESO" ? "−" : ""}{formatMoney(m.monto)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

// Conceptos de un periodo en una línea: "Aportes de ahorro $X (3) · ...".
const ConceptosPeriodo = ({ porTipo }) => (
  <div className="flex flex-wrap gap-x-3 gap-y-0.5">
    {porTipo.map((t) => (
      <span key={t.tipo} className="inline-flex items-center gap-1 text-[11px] text-slate-500 whitespace-nowrap">
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: NATURALEZAS[t.naturaleza]?.color }} />
        {t.etiqueta} <strong className="text-slate-700">{formatMoney(t.total)}</strong>
        {t.cantidad > 1 && <span className="text-slate-400">({t.cantidad})</span>}
      </span>
    ))}
  </div>
);

const ORIGEN_EVENTO = { actividad: "Evento", rifa: "Rifa", reunion: "Reunión" };

const Tarjeta = ({ icono: Icono, titulo, valor, detalle, color }) => (
  <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-4">
    <p className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
      <Icono className="w-4 h-4" style={color ? { color } : undefined} /> {titulo}
    </p>
    <p className="text-2xl font-black text-slate-800 mt-1">{valor}</p>
    {detalle && <p className="text-[11px] text-slate-500 mt-0.5">{detalle}</p>}
  </div>
);

const Resultados = ({ datos }) => {
  const [verTabla, setVerTabla] = useState(false);
  const [abiertos, setAbiertos] = useState({});
  const { totales, serie, por_tipo: porTipo, por_evento: porEvento, granularidad } = datos;
  // Estadísticas guardadas antes de este cambio no traen el detalle por movimiento.
  const movimientos = datos.movimientos || [];
  const tieneDetalle = Array.isArray(datos.movimientos);
  const movimientosDe = (periodo) => movimientos.filter((m) => m.periodo === periodo);
  const alternar = (periodo) => setAbiertos((a) => ({ ...a, [periodo]: !a[periodo] }));
  if (!totales.cantidad) {
    return (
      <div className="bg-white rounded-2xl border border-dashed border-slate-300 p-10 text-center text-sm text-slate-500">
        No hay movimientos registrados con estos filtros.
      </div>
    );
  }
  return (
    <div className="space-y-6 viz-root">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Tarjeta icono={TrendingUp} titulo="Ingresos" valor={formatMoney(totales.ingresos)} color="var(--serie-ingreso)" />
        <Tarjeta icono={TrendingDown} titulo="Egresos" valor={formatMoney(totales.egresos)} color="var(--serie-egreso)" />
        <Tarjeta icono={Scale} titulo="Balance" valor={formatMoney(totales.balance)} detalle="Ingresos menos egresos" />
        <Tarjeta icono={Hash} titulo="Movimientos" valor={totales.cantidad}
                 detalle={totales.otros ? `Multas impuestas: ${formatMoney(totales.otros)}` : null} />
      </div>

      <section className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <div>
            <h2 className="font-bold text-slate-800">Ingresos y egresos {granularidad === "dia" ? "por día" : "por mes"}</h2>
            <Leyenda series={[NATURALEZAS.INGRESO, NATURALEZAS.EGRESO]} />
          </div>
          <button onClick={() => setVerTabla((v) => !v)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-slate-600 bg-slate-100 hover:bg-slate-200">
            <Table2 className="w-4 h-4" /> {verTabla ? "Ver gráfica" : "Ver tabla"}
          </button>
        </div>
        {verTabla ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-slate-500 border-b border-slate-100">
                <th className="py-2 pr-3">Periodo</th>
                {serie.some((p) => p.por_tipo) && <th className="py-2 pr-3">Conceptos</th>}
                <th className="py-2 pr-3 text-right">Ingresos</th>
                <th className="py-2 pr-3 text-right">Egresos</th><th className="py-2 pr-3 text-right">Otros</th><th className="py-2 text-right">Balance</th>
              </tr></thead>
              <tbody>
                {serie.filter((p) => p.ingresos || p.egresos || p.otros).map((p) => {
                  const abierto = !!abiertos[p.periodo];
                  const lista = tieneDetalle ? movimientosDe(p.periodo) : [];
                  return (
                    <React.Fragment key={p.periodo}>
                      <tr className="border-b border-slate-50 text-slate-700 align-top">
                        <td className="py-1.5 pr-3 font-semibold whitespace-nowrap">
                          {tieneDetalle ? (
                            <button type="button" onClick={() => alternar(p.periodo)} aria-expanded={abierto}
                                    className="inline-flex items-center gap-1 hover:text-emerald-700"
                                    title={abierto ? "Ocultar los movimientos" : "Ver cada movimiento de este periodo"}>
                              <ChevronDown className={`w-3.5 h-3.5 transition-transform ${abierto ? "" : "-rotate-90"}`} />
                              {etiquetaPeriodo(p.periodo, granularidad)}
                            </button>
                          ) : etiquetaPeriodo(p.periodo, granularidad)}
                        </td>
                        {serie.some((x) => x.por_tipo) && (
                          <td className="py-1.5 pr-3"><div className="max-w-[20rem]"><ConceptosPeriodo porTipo={p.por_tipo || []} /></div></td>
                        )}
                        <td className="py-1.5 pr-3 text-right">{formatMoney(p.ingresos)}</td>
                        <td className="py-1.5 pr-3 text-right">{formatMoney(p.egresos)}</td>
                        <td className="py-1.5 pr-3 text-right">{formatMoney(p.otros)}</td>
                        <td className="py-1.5 text-right font-bold">{formatMoney(p.balance)}</td>
                      </tr>
                      {abierto && (
                        <tr className="border-b border-slate-100">
                          <td colSpan={6} className="py-2"><DetallePeriodo movimientos={lista} /></td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <GraficaEvolucion serie={serie} granularidad={granularidad} />
        )}
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        <section className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-4 sm:p-5">
          <h2 className="font-bold text-slate-800">Por tipo de movimiento</h2>
          <div className="mb-3"><Leyenda series={Object.values(NATURALEZAS).filter((n) => porTipo.some((t) => NATURALEZAS[t.naturaleza] === n))} /></div>
          <GraficaPorTipo porTipo={porTipo} />
        </section>

        {porEvento.length > 0 && (
          <section className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-4 sm:p-5">
            <h2 className="font-bold text-slate-800 mb-3">Por evento</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs text-slate-500 border-b border-slate-100">
                  <th className="py-2 pr-3">Evento</th><th className="py-2 pr-3">Tipo</th><th className="py-2 pr-3 text-right">Ingresos</th>
                  <th className="py-2 pr-3 text-right">Inversión</th><th className="py-2 text-right">Balance</th>
                </tr></thead>
                <tbody>
                  {porEvento.map((e) => (
                    <tr key={e.evento} className="border-b border-slate-50 text-slate-700">
                      <td className="py-1.5 pr-3"><p className="font-semibold">{e.nombre}</p><p className="text-[11px] text-slate-400">{formatDate(e.fecha)}</p></td>
                      <td className="py-1.5 pr-3 text-xs text-slate-500">{ORIGEN_EVENTO[String(e.evento).split("-")[0]] || e.origen || "-"}</td>
                      <td className="py-1.5 pr-3 text-right">{formatMoney(e.ingresos)}</td>
                      <td className="py-1.5 pr-3 text-right">{formatMoney(e.egresos)}</td>
                      <td className="py-1.5 text-right font-bold">{formatMoney(e.balance)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </div>
  );
};

const FILTROS_INICIALES = { modo: "todo", mesDesde: "", mesHasta: "", fechaDesde: "", fechaHasta: "", evento: "", tipos: [] };

// Filtros del formulario -> filtros que entiende el backend.
const aFiltrosApi = (f) => {
  let fecha_desde = null, fecha_hasta = null;
  if (f.modo === "meses" && f.mesDesde) {
    fecha_desde = `${f.mesDesde}-01`;
    fecha_hasta = ultimoDiaMes(f.mesHasta || f.mesDesde);
  } else if (f.modo === "fechas") {
    fecha_desde = f.fechaDesde || null;
    fecha_hasta = f.fechaHasta || null;
  }
  return { modo: f.modo, fecha_desde, fecha_hasta, evento: f.evento || null, tipos: f.tipos };
};

const errorDe = (err, porDefecto) => {
  const d = err.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg.replace(/^Value error, /, "");
  return porDefecto;
};

export const Estadisticas = () => {
  const { user } = useAuth();
  const isAdmin = !!(user?.is_admin || user?.is_developer); // El Desarrollador también tiene acceso total.
  const [opciones, setOpciones] = useState(null);
  const [form, setForm] = useState(FILTROS_INICIALES);
  const [aplicados, setAplicados] = useState(aFiltrosApi(FILTROS_INICIALES));
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [guardadas, setGuardadas] = useState([]);
  const [viendo, setViendo] = useState(null); // Estadística guardada en pantalla.
  const [nombre, setNombre] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [aviso, setAviso] = useState("");

  const cargarGuardadas = useCallback(async () => {
    try {
      setGuardadas((await api.get("/estadisticas/guardadas")).data);
    } catch (err) {
      console.error(err);
    }
  }, []);

  useEffect(() => {
    api.get("/estadisticas/opciones").then((r) => setOpciones(r.data)).catch((err) => console.error(err));
    cargarGuardadas();
  }, [cargarGuardadas]);

  const consultar = useCallback(async (filtros) => {
    setCargando(true);
    setError("");
    try {
      const res = await api.get("/estadisticas", { params: {
        modo: filtros.modo,
        fecha_desde: filtros.fecha_desde || undefined,
        fecha_hasta: filtros.fecha_hasta || undefined,
        evento: filtros.evento || undefined,
        tipos: filtros.tipos.length ? filtros.tipos.join(",") : undefined,
      } });
      setDatos(res.data);
      setAplicados(filtros);
    } catch (err) {
      console.error(err);
      setError(errorDe(err, "No se pudieron calcular las estadísticas."));
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => { consultar(aFiltrosApi(FILTROS_INICIALES)); }, [consultar]);

  const aplicar = (e) => {
    e.preventDefault();
    const f = aFiltrosApi(form);
    if (f.fecha_desde && f.fecha_hasta && f.fecha_hasta < f.fecha_desde) {
      setError("La fecha final no puede ser anterior a la fecha inicial.");
      return;
    }
    setViendo(null);
    setAviso("");
    consultar(f);
  };

  const cambiar = (campo, valor) => setForm((f) => ({ ...f, [campo]: valor }));
  const alternarTipo = (tipo) => setForm((f) => ({
    ...f, tipos: f.tipos.includes(tipo) ? f.tipos.filter((t) => t !== tipo) : [...f.tipos, tipo],
  }));
  const alternarNaturaleza = (naturaleza) => {
    const delGrupo = (opciones?.tipos || []).filter((t) => t.naturaleza === naturaleza).map((t) => t.tipo);
    setForm((f) => {
      const todos = delGrupo.every((t) => f.tipos.includes(t));
      return { ...f, tipos: todos ? f.tipos.filter((t) => !delGrupo.includes(t)) : [...new Set([...f.tipos, ...delGrupo])] };
    });
  };

  const guardar = async (e) => {
    e.preventDefault();
    if (!nombre.trim()) return;
    setGuardando(true);
    setAviso("");
    try {
      const res = await api.post("/estadisticas/guardadas", { nombre: nombre.trim(), filtros: aplicados });
      setNombre("");
      setAviso(`Estadística "${res.data.nombre}" guardada.`);
      cargarGuardadas();
    } catch (err) {
      console.error(err);
      setAviso(errorDe(err, "No se pudo guardar la estadística."));
    } finally {
      setGuardando(false);
    }
  };

  const ver = async (id) => {
    try {
      setViendo((await api.get(`/estadisticas/guardadas/${id}`)).data);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      console.error(err);
      setError(errorDe(err, "No se pudo abrir la estadística guardada."));
    }
  };

  const eliminar = async (g) => {
    if (!window.confirm(`¿Eliminar la estadística guardada "${g.nombre}"? Esta acción no se puede deshacer.`)) return;
    try {
      await api.delete(`/estadisticas/guardadas/${g.id}`);
      if (viendo?.id === g.id) setViendo(null);
      cargarGuardadas();
    } catch (err) {
      console.error(err);
      setError(errorDe(err, "No se pudo eliminar la estadística."));
    }
  };

  const tiposPorNaturaleza = useMemo(() => {
    const grupos = {};
    (opciones?.tipos || []).forEach((t) => { (grupos[t.naturaleza] ||= []).push(t); });
    return grupos;
  }, [opciones]);

  const enPantalla = viendo ? viendo.resultados : datos;
  const campo = "px-3 py-2 bg-white border border-slate-200 rounded-xl text-sm text-slate-700 outline-none focus:border-purple-400 focus:ring-2 focus:ring-purple-100";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl md:text-3xl font-black text-slate-800 tracking-tight flex items-center gap-2.5">
          <ChartColumn className="w-7 h-7 text-purple-600" />
          Estadísticas
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Cómo se ha movido el dinero de la natillera{datos?.anio ? ` en ${datos.anio}` : ""}, con los movimientos registrados en el sistema.
        </p>
      </div>

      {/* Filtros */}
      <form onSubmit={aplicar} className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-4 sm:p-5 space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <label className="text-xs font-bold text-slate-500 space-y-1">
            <span>Periodo</span>
            <select value={form.modo} onChange={(e) => cambiar("modo", e.target.value)} className={`${campo} w-full`}>
              <option value="todo">Todo el año</option>
              <option value="meses">Por meses</option>
              <option value="fechas">Por fechas</option>
            </select>
          </label>
          {form.modo === "meses" && (<>
            <label className="text-xs font-bold text-slate-500 space-y-1">
              <span>Mes inicial</span>
              <input type="month" required value={form.mesDesde} onChange={(e) => cambiar("mesDesde", e.target.value)} className={`${campo} w-full`} />
            </label>
            <label className="text-xs font-bold text-slate-500 space-y-1">
              <span>Mes final (opcional)</span>
              <input type="month" value={form.mesHasta} min={form.mesDesde || undefined} onChange={(e) => cambiar("mesHasta", e.target.value)} className={`${campo} w-full`} />
            </label>
          </>)}
          {form.modo === "fechas" && (<>
            <label className="text-xs font-bold text-slate-500 space-y-1">
              <span>Fecha inicial</span>
              <input type="date" value={form.fechaDesde} onChange={(e) => cambiar("fechaDesde", e.target.value)} className={`${campo} w-full`} />
            </label>
            <label className="text-xs font-bold text-slate-500 space-y-1">
              <span>Fecha final</span>
              <input type="date" value={form.fechaHasta} min={form.fechaDesde || undefined} onChange={(e) => cambiar("fechaHasta", e.target.value)} className={`${campo} w-full`} />
            </label>
          </>)}
          <label className="text-xs font-bold text-slate-500 space-y-1">
            <span>Evento</span>
            <select value={form.evento} onChange={(e) => cambiar("evento", e.target.value)} className={`${campo} w-full`}>
              <option value="">Todos los movimientos</option>
              {["Evento", "Rifa", "Reunión"].map((cat) => {
                const lista = (opciones?.eventos || []).filter((ev) => ev.categoria === cat);
                return lista.length ? (
                  <optgroup key={cat} label={cat === "Evento" ? "Eventos" : cat === "Rifa" ? "Rifas" : "Reuniones"}>
                    {lista.map((ev) => <option key={ev.clave} value={ev.clave}>{ev.nombre} ({formatDate(ev.fecha)})</option>)}
                  </optgroup>
                ) : null;
              })}
            </select>
          </label>
        </div>

        <div>
          <p className="text-xs font-bold text-slate-500 mb-2">
            Tipo de movimiento <span className="font-normal">({form.tipos.length ? `${form.tipos.length} elegidos` : "todos"})</span>
          </p>
          <div className="space-y-2">
            {Object.entries(tiposPorNaturaleza).map(([naturaleza, tipos]) => (
              <div key={naturaleza} className="flex flex-wrap items-center gap-1.5">
                <button type="button" onClick={() => alternarNaturaleza(naturaleza)}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold text-slate-700 bg-slate-100 hover:bg-slate-200 viz-root">
                  <span className="w-2.5 h-2.5 rounded-sm" style={{ background: NATURALEZAS[naturaleza].color }} />
                  {NATURALEZAS[naturaleza].etiqueta}
                </button>
                {tipos.map((t) => {
                  const activo = form.tipos.includes(t.tipo);
                  return (
                    <button key={t.tipo} type="button" onClick={() => alternarTipo(t.tipo)} aria-pressed={activo}
                            className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-colors ${
                              activo ? "bg-purple-50 border-purple-300 text-purple-800" : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
                            }`}>
                      {t.etiqueta}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button type="submit" className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold text-white bg-purple-600 hover:bg-purple-700">
            <Filter className="w-4 h-4" /> Generar estadística
          </button>
          <button type="button" onClick={() => setForm(FILTROS_INICIALES)} className="px-4 py-2 rounded-xl text-sm font-bold text-slate-600 bg-slate-100 hover:bg-slate-200">
            Limpiar filtros
          </button>
        </div>
      </form>

      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-2xl text-rose-700 text-sm font-semibold flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 shrink-0" /> {error}
        </div>
      )}

      {/* Encabezado de lo que se está viendo */}
      {viendo ? (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-2xl bg-purple-50 border border-purple-200 text-purple-900">
          <div className="text-sm">
            <p className="font-bold">Estadística guardada: {viendo.nombre}</p>
            <p className="text-xs">Año {viendo.anio} · {describirFiltros(viendo.filtros, opciones)} · guardada el {formatDate(viendo.created_at)}. Muestra los resultados de ese momento.</p>
          </div>
          <button onClick={() => setViendo(null)} className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-white bg-purple-600 hover:bg-purple-700">
            <ArrowLeft className="w-4 h-4" /> Volver a la consulta actual
          </button>
        </div>
      ) : datos && (
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          <p className="text-sm text-slate-600"><strong>{describirFiltros(aplicados, opciones)}</strong>
            {datos.rango?.desde && <span className="text-slate-400"> · {formatDate(datos.rango.desde)} a {formatDate(datos.rango.hasta)}</span>}
          </p>
          {isAdmin && (
            <form onSubmit={guardar} className="flex gap-2">
              <input value={nombre} onChange={(e) => setNombre(e.target.value)} maxLength={120} required
                     placeholder="Nombre, ej. Enero a marzo" aria-label="Nombre de la estadística" className={`${campo} min-w-0 flex-1 sm:w-64`} />
              <button type="submit" disabled={guardando || !nombre.trim()}
                      className="shrink-0 inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm font-bold text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50">
                <Save className="w-4 h-4" /> {guardando ? "Guardando..." : "Guardar"}
              </button>
            </form>
          )}
        </div>
      )}
      {aviso && !viendo && <p className="text-sm font-semibold text-emerald-700">{aviso}</p>}

      {cargando && !enPantalla ? (
        <div className="py-16 text-center text-slate-400 text-sm">
          <div className="w-6 h-6 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
          Calculando estadísticas...
        </div>
      ) : enPantalla && <Resultados key={viendo ? `g${viendo.id}` : "actual"} datos={enPantalla} />}

      {/* Estadísticas guardadas */}
      <section className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-4 sm:p-5">
        <h2 className="font-bold text-slate-800 mb-3">Estadísticas guardadas ({guardadas.length})</h2>
        {guardadas.length === 0 ? (
          <p className="text-sm text-slate-500">Aún no hay estadísticas guardadas.{isAdmin ? " Genera una y guárdala con un nombre." : ""}</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {guardadas.map((g) => (
              <li key={g.id} className={`py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2 ${viendo?.id === g.id ? "bg-purple-50/60 -mx-2 px-2 rounded-xl" : ""}`}>
                <div className="min-w-0">
                  <p className="font-semibold text-slate-800 truncate">{g.nombre}</p>
                  <p className="text-xs text-slate-500">
                    Año {g.anio} · {describirFiltros(g.filtros, opciones)} · {formatDate(g.created_at)}{g.usuario_nombre ? ` · ${g.usuario_nombre}` : ""}
                  </p>
                  <p className="text-xs text-slate-600 mt-0.5">
                    Ingresos {formatMoney(g.totales.ingresos)} · Egresos {formatMoney(g.totales.egresos)} · Balance <strong>{formatMoney(g.totales.balance)}</strong>
                  </p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button onClick={() => ver(g.id)} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-purple-700 bg-purple-50 hover:bg-purple-100">
                    <Eye className="w-4 h-4" /> Ver
                  </button>
                  {isAdmin && (
                    <button onClick={() => eliminar(g)} aria-label={`Eliminar ${g.nombre}`} className="inline-flex items-center px-2 py-1.5 rounded-lg text-xs font-bold text-rose-600 bg-rose-50 hover:bg-rose-100">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
};
