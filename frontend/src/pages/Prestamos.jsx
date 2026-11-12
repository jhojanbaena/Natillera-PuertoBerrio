import React, { useState, useEffect, useRef } from "react";
import {
  HandCoins, Plus, ChevronDown, ChevronUp, Trash2, Edit, AlertTriangle, Info, CheckCircle2, Clock,
} from "lucide-react";
import { useSearchParams } from "react-router-dom";
import api from "../api/client";
import { Modal } from "../components/Modal";
import { InteresesMes } from "../components/InteresesMes";
import { AbonosLineas } from "../components/AbonosLineas";
import { MoneyInput } from "../components/MoneyInput";
import { formatMoney, formatDate, fechaLocalISO } from "../utils/formatters";

const REGLA_MORA = "MORA_7_10";
// Regla vigente: 10 % mensual sobre el capital pendiente (7 % socio / 3 % bien común).
const REGLA_REPARTO = "REPARTO_7_3";
const CERRADOS = ["PAGADO"];

const FILTROS = [
  { id: "TODOS", texto: "Todos" },
  { id: "PENDIENTE", texto: "Al día" },
  { id: "EN_MORA", texto: "En mora" },
  { id: "PAGADO", texto: "Pagados" },
];

const ESTADO_TEXTO = { PENDIENTE: "Al día", EN_MORA: "En mora", PAGADO: "Pagado" };

const DESTINO_TEXTO = {
  AHORRO_PERSONAL: "Ahorro personal del socio (cuotas 1 a 3)",
  BIEN_COMUN: "Bien común (desde la cuota 4)",
  REPARTO_7_3: "7 % para el ahorro del socio y 3 % para el bien común",
};

// Préstamos con intereses mes a mes (regla 7 %/10 % anterior o regla 7 %/3 % vigente).
const esMora = (p) => p?.regla_interes === REGLA_MORA || p?.regla_interes === REGLA_REPARTO;
const esReparto = (p) => p?.regla_interes === REGLA_REPARTO;
const num = (v) => Number(v || 0);
const pct = (v) => `${num(v).toLocaleString("es-CO", { maximumFractionDigits: 2 })} %`;

const mensajeError = (err, porDefecto) => {
  const detail = err.response?.data?.detail;
  return (Array.isArray(detail) ? detail.map((item) => item.msg).join("; ") : detail) || porDefecto;
};

const inputClass = "w-full px-3.5 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500 text-sm";
const labelClass = "block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1";

const formPrestamoInicial = () => ({
  socio_id: "", monto_prestado: "", tasa_interes: "10", regla_interes: REGLA_REPARTO,
  numero_cuotas: 4, fecha_prestamo: fechaLocalISO(),
});

const formAbonoInicial = () => ({
  monto_abonado: "", monto_capital: "", monto_interes: "0", fecha_pago: fechaLocalISO(),
  numero_cuota: "", tasa_aplicada: "",
});

export const Prestamos = () => {
  const [prestamos, setPrestamos] = useState([]);
  const [socios, setSocios] = useState([]);
  const [consolidado, setConsolidado] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [filtro, setFiltro] = useState("TODOS");
  const [vista, setVista] = useState("CARTERA");

  // Modal nuevo préstamo
  const [isPrestamoModalOpen, setIsPrestamoModalOpen] = useState(false);
  const [prestamoForm, setPrestamoForm] = useState(formPrestamoInicial);
  const [submittingPrestamo, setSubmittingPrestamo] = useState(false);

  // Modal abonar cuota
  const [isAbonoModalOpen, setIsAbonoModalOpen] = useState(false);
  const [selectedPrestamo, setSelectedPrestamo] = useState(null);
  const [abonoForm, setAbonoForm] = useState(formAbonoInicial);
  const [submittingAbono, setSubmittingAbono] = useState(false);
  const [editingAbono, setEditingAbono] = useState(null);
  const [vistaAbono, setVistaAbono] = useState(null);
  const [errorVistaAbono, setErrorVistaAbono] = useState("");
  // Al editar, la primera vista previa no debe reemplazar los valores guardados.
  const autoCompletar = useRef(true);

  const fetchAll = async () => {
    try {
      setLoading(true);
      const [presRes, socRes, conRes] = await Promise.all([
        api.get("/prestamos"),
        api.get("/socios"),
        api.get("/prestamos/consolidado/global"),
      ]);
      setPrestamos(presRes.data);
      // Mantener al día el préstamo abierto en el modal de abono.
      setSelectedPrestamo((actual) => (actual ? presRes.data.find((p) => p.id === actual.id) || actual : actual));
      setSocios(socRes.data);
      setConsolidado(conRes.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  // Enlace desde el estado de cuenta del socio: /prestamos?prestamo=ID despliega y resalta ese préstamo.
  const [searchParams] = useSearchParams();
  const prestamoEnfocado = Number(searchParams.get("prestamo")) || null;
  useEffect(() => {
    if (loading || !prestamoEnfocado || !prestamos.some((p) => p.id === prestamoEnfocado)) return;
    setExpandedId(prestamoEnfocado);
    requestAnimationFrame(() => {
      document.getElementById(`prestamo-${prestamoEnfocado}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }, [loading, prestamoEnfocado, prestamos]);

  // ---------------------------------------------------------------- Vista previa del abono (7 % / 10 %)
  useEffect(() => {
    // Al abrir o cerrar el modal la vista previa se limpia en abrirAbono / cerrarAbono.
    if (!isAbonoModalOpen || !esMora(selectedPrestamo) || !abonoForm.fecha_pago) return;
    let cancelado = false;
    const params = { fecha_pago: abonoForm.fecha_pago };
    if (abonoForm.numero_cuota) params.numero_cuota = abonoForm.numero_cuota;
    if (editingAbono) params.excluir_abono_id = editingAbono.id;
    api.get(`/prestamos/${selectedPrestamo.id}/abonos/vista-previa`, { params })
      .then(({ data }) => {
        if (cancelado) return;
        setVistaAbono(data);
        setErrorVistaAbono("");
        setAbonoForm((form) => {
          const siguiente = { ...form, numero_cuota: String(data.numero_cuota) };
          if (!autoCompletar.current) return siguiente;
          const tasa = data.tasa_sugerida;
          return {
            ...siguiente,
            tasa_aplicada: String(num(tasa)),
            monto_interes: String(num(num(tasa) === num(data.tasa_mora) ? data.pendiente_tasa_mora : data.pendiente_tasa_normal)),
            monto_capital: form.monto_capital || "0",
          };
        });
        autoCompletar.current = true;
      })
      .catch((err) => { if (!cancelado) setErrorVistaAbono(mensajeError(err, "No se pudo calcular la tasa")); });
    return () => { cancelado = true; };
  }, [isAbonoModalOpen, selectedPrestamo, editingAbono, abonoForm.fecha_pago, abonoForm.numero_cuota]);

  const pendienteSegunTasa = (tasa) => {
    if (!vistaAbono) return 0;
    return num(tasa) === num(vistaAbono.tasa_mora) ? num(vistaAbono.pendiente_tasa_mora) : num(vistaAbono.pendiente_tasa_normal);
  };

  const elegirTasa = (tasa) => {
    setAbonoForm((form) => ({ ...form, tasa_aplicada: String(num(tasa)), monto_interes: String(pendienteSegunTasa(tasa)) }));
  };

  // Abonar en estilo lista (líneas de capital, interés y fecha).
  const [listaAbonosId, setListaAbonosId] = useState(null);
  const prestamoLista = prestamos.find((p) => p.id === listaAbonosId) || null;

  const abrirAbono = (prestamo) => {
    autoCompletar.current = true;
    setSelectedPrestamo(prestamo);
    setEditingAbono(null);
    setVistaAbono(null);
    setErrorVistaAbono("");
    setAbonoForm(formAbonoInicial());
    setIsAbonoModalOpen(true);
  };

  const cerrarAbono = () => {
    setIsAbonoModalOpen(false);
    setEditingAbono(null);
    setVistaAbono(null);
  };

  const handleCreatePrestamo = async (e) => {
    e.preventDefault();
    if (!prestamoForm.socio_id || !prestamoForm.monto_prestado || !prestamoForm.numero_cuotas) {
      alert("Completa el socio, el monto y el número de cuotas.");
      return;
    }

    try {
      setSubmittingPrestamo(true);
      await api.post("/prestamos", {
        socio_id: Number(prestamoForm.socio_id),
        monto_prestado: prestamoForm.monto_prestado,
        regla_interes: prestamoForm.regla_interes,
        tasa_interes: prestamoForm.regla_interes === REGLA_REPARTO ? "10" : prestamoForm.regla_interes === REGLA_MORA ? "7" : (prestamoForm.tasa_interes || "0"),
        numero_cuotas: Number(prestamoForm.numero_cuotas),
        fecha_prestamo: prestamoForm.fecha_prestamo || null,
      });
      setIsPrestamoModalOpen(false);
      setPrestamoForm(formPrestamoInicial());
      await fetchAll();
    } catch (err) {
      alert(mensajeError(err, "Error al registrar el préstamo."));
    } finally {
      setSubmittingPrestamo(false);
    }
  };

  const handleAbono = async (e) => {
    e.preventDefault();
    const mora = esMora(selectedPrestamo);
    const montoCapital = Number(abonoForm.monto_capital || "0");
    const montoInteres = Number(abonoForm.monto_interes || "0");
    // En la regla 7 %/10 % el total es la suma de capital e interés.
    const montoAbonado = mora ? montoCapital + montoInteres : Number(abonoForm.monto_abonado);

    if (!Number.isFinite(montoAbonado) || montoAbonado <= 0) {
      alert("Ingresa un monto total válido para el abono.");
      return;
    }
    if (!Number.isFinite(montoCapital) || montoCapital < 0 || !Number.isFinite(montoInteres) || montoInteres < 0) {
      alert("Ingresa valores válidos para capital e interés.");
      return;
    }
    if (!mora && Math.round((montoCapital + montoInteres) * 100) !== Math.round(montoAbonado * 100)) {
      alert("El capital y el interés deben sumar exactamente el monto total abonado.");
      return;
    }

    try {
      setSubmittingAbono(true);
      const payload = mora
        ? {
          prestamo_id: selectedPrestamo.id,
          monto_abonado: montoAbonado.toFixed(2),
          monto_capital: montoCapital.toFixed(2),
          monto_interes: montoInteres.toFixed(2),
          numero_cuota: Number(abonoForm.numero_cuota) || undefined,
          tasa_aplicada: abonoForm.tasa_aplicada || undefined,
          fecha_pago: abonoForm.fecha_pago || undefined,
        }
        : {
          prestamo_id: selectedPrestamo.id,
          monto_abonado: abonoForm.monto_abonado,
          monto_capital: abonoForm.monto_capital,
          monto_interes: abonoForm.monto_interes || "0",
          numero_cuota: editingAbono?.numero_cuota || selectedPrestamo.cuotas_pagadas + 1,
          fecha_pago: abonoForm.fecha_pago || undefined,
        };
      if (editingAbono) {
        await api.put(`/prestamos/${selectedPrestamo.id}/abonos/${editingAbono.id}`, payload);
      } else {
        await api.post(`/prestamos/${selectedPrestamo.id}/abonos`, payload);
      }
      cerrarAbono();
      setAbonoForm(formAbonoInicial());
      await fetchAll();
    } catch (err) {
      alert(mensajeError(err, "Error al registrar el abono."));
    } finally {
      setSubmittingAbono(false);
    }
  };

  const openEditAbono = (prestamo, abono) => {
    autoCompletar.current = !esMora(prestamo);
    setSelectedPrestamo(prestamo);
    setEditingAbono(abono);
    setVistaAbono(null);
    setAbonoForm({
      monto_abonado: String(abono.monto_abonado),
      monto_capital: String(abono.monto_capital),
      monto_interes: String(abono.monto_interes),
      fecha_pago: fechaLocalISO(abono.fecha_pago),
      numero_cuota: String(abono.numero_cuota),
      tasa_aplicada: abono.tasa_aplicada != null ? String(num(abono.tasa_aplicada)) : "",
    });
    setIsAbonoModalOpen(true);
  };

  const handleDeletePrestamo = async (prestamo) => {
    if (getTotalPendiente(prestamo) > 0) {
      alert("No se puede eliminar el préstamo mientras tenga deuda pendiente.");
      return;
    }

    const confirmed = window.confirm(
      `¿Eliminar el préstamo #${prestamo.id} y todos sus abonos? Esta acción no se puede deshacer.`
    );
    if (!confirmed) return;

    try {
      await api.delete(`/prestamos/${prestamo.id}`);
      if (expandedId === prestamo.id) setExpandedId(null);
      await fetchAll();
    } catch (err) {
      alert(mensajeError(err, "Error al eliminar el préstamo."));
    }
  };

  const estadoColor = (estado) => {
    if (estado === "PAGADO") return "bg-emerald-100 text-emerald-800";
    if (estado === "EN_MORA") return "bg-rose-100 text-rose-800";
    return "bg-amber-100 text-amber-800";
  };

  const conteo = (estado) => prestamos.filter((p) => estado === "TODOS" || p.estado === estado).length;
  const prestamosEnMora = conteo("EN_MORA");
  const prestamosVisibles = prestamos.filter((p) => filtro === "TODOS" || p.estado === filtro);

  const getSocioNombre = (socioId) => (
    socios.find((socio) => socio.id === socioId)?.nombre || `Socio #${socioId}`
  );

  const getTotalInicial = (prestamo) => (
    Number(prestamo.monto_prestado) + Number(prestamo.total_intereses || 0)
  );

  const getTotalAbonado = (prestamo) => (
    (prestamo.abonos || []).reduce((total, abono) => total + Number(abono.monto_abonado || 0), 0)
  );

  const getCapitalAbonado = (prestamo) => (
    (prestamo.abonos || []).reduce((total, abono) => total + Number(abono.monto_capital || 0), 0)
  );

  const getInteresesAbonados = (prestamo) => (
    (prestamo.abonos || []).reduce((total, abono) => total + Number(abono.monto_interes || 0), 0)
  );

  const getCapitalPendiente = (prestamo) => (
    Math.max(0, Number(prestamo.monto_prestado) - getCapitalAbonado(prestamo))
  );

  const getInteresesPendientes = (prestamo) => (
    Math.max(0, Number(prestamo.total_intereses || 0) - getInteresesAbonados(prestamo))
  );

  const getTotalPendiente = (prestamo) => (
    Math.max(0, getTotalInicial(prestamo) - getTotalAbonado(prestamo))
  );

  const tasaElegida = num(abonoForm.tasa_aplicada);
  const tasaManual = vistaAbono && abonoForm.tasa_aplicada && tasaElegida !== num(vistaAbono.tasa_sugerida);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-black text-slate-800 tracking-tight flex items-center gap-2.5">
            <HandCoins className="w-7 h-7 text-purple-600" />
            Préstamos y Cartera Activa
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Gestión de créditos, cuotas y amortización de capital e intereses.</p>
        </div>
        <button
          onClick={() => setIsPrestamoModalOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-purple-600 hover:bg-purple-700 text-white text-sm font-bold rounded-xl shadow-md shadow-purple-600/20 transition-all active:scale-95"
        >
          <Plus className="w-4 h-4" /> Nuevo Préstamo
        </button>
      </div>

      {/* Consolidado global */}
      {consolidado && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-sm">
            <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">Total Desembolsado</p>
            <p className="text-2xl font-black text-slate-800 mt-1">{formatMoney(consolidado.monto_global_prestado)}</p>
          </div>
          <div className="bg-white rounded-2xl p-5 border border-purple-200/80 shadow-sm bg-purple-50/30">
            <p className="text-xs font-bold text-purple-600 uppercase tracking-wider">Saldo Pendiente Activo</p>
            <p className="text-2xl font-black text-purple-700 mt-1">{formatMoney(consolidado.monto_global_saldo_pendiente)}</p>
          </div>
          <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-sm">
            <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">Préstamos registrados</p>
            <p className="text-2xl font-black text-slate-800 mt-1">{consolidado.total_prestamos_historicos}</p>
          </div>
          <div className="bg-white rounded-2xl p-5 border border-emerald-200/80 shadow-sm bg-emerald-50/30">
            <p className="text-xs font-bold text-emerald-600 uppercase tracking-wider">Préstamos en circulación</p>
            <p className="text-2xl font-black text-emerald-700 mt-1">{consolidado.total_prestamos_activos}</p>
            {prestamosEnMora > 0 && (
              <p className="text-xs font-bold text-rose-600 mt-1 flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5" /> {prestamosEnMora} en mora
              </p>
            )}
          </div>
        </div>
      )}

      {/* Pestañas: cartera completa o lista de intereses del mes */}
      <div className="inline-flex p-1 bg-slate-100 rounded-xl" role="tablist" aria-label="Vista de préstamos">
        {[
          { id: "CARTERA", texto: "Cartera" },
          { id: "INTERESES", texto: "Intereses del mes" },
        ].map((v) => (
          <button
            key={v.id}
            role="tab"
            aria-selected={vista === v.id}
            onClick={() => setVista(v.id)}
            className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-colors ${
              vista === v.id ? "bg-white text-purple-700 shadow-sm" : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {v.texto}
          </button>
        ))}
      </div>

      {vista === "INTERESES" ? (
        <InteresesMes prestamos={prestamos} socios={socios} onRegistrado={fetchAll} />
      ) : (
      <>
      {/* Filtros por estado */}
      <div className="flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Filtrar préstamos por estado">
        {FILTROS.map((f) => (
          <button
            key={f.id}
            role="tab"
            aria-selected={filtro === f.id}
            onClick={() => setFiltro(f.id)}
            className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-bold border transition-colors ${
              filtro === f.id
                ? "bg-purple-600 text-white border-purple-600"
                : "bg-white text-slate-600 border-slate-200 hover:border-purple-300"
            }`}
          >
            {f.texto} <span className={filtro === f.id ? "text-purple-100" : "text-slate-400"}>({conteo(f.id)})</span>
          </button>
        ))}
      </div>

      {/* Lista de préstamos */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-16 text-center text-slate-400 text-sm">
            <div className="w-6 h-6 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
            Cargando cartera de préstamos...
          </div>
        ) : prestamosVisibles.length > 0 ? (
          <div className="divide-y divide-slate-100">
            {prestamosVisibles.map((p) => {
              const abierto = !CERRADOS.includes(p.estado);
              return (
                <div
                  key={p.id}
                  id={`prestamo-${p.id}`}
                  className={`p-4 sm:p-5 hover:bg-slate-50/40 transition-colors ${
                    prestamoEnfocado === p.id ? "ring-2 ring-inset ring-purple-300 bg-purple-50/30" : ""
                  }`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h4 className="font-bold text-slate-800 text-sm">{getSocioNombre(p.socio_id)}</h4>
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${estadoColor(p.estado)}`}>{ESTADO_TEXTO[p.estado] || p.estado}</span>
                        {esReparto(p) ? (
                          <span
                            title="10 % mensual sobre el capital pendiente: 7 % para el socio y 3 % para el bien común"
                            className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200"
                          >
                            10 % · 7 % socio / 3 % B. común
                          </span>
                        ) : esMora(p) ? (
                          abierto && p.tasa_vigente != null && (
                            <span
                              title="Tasa que corresponde si el próximo mes pendiente se paga hoy"
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                num(p.tasa_vigente) > num(p.tasa_interes) ? "bg-rose-50 text-rose-700 border border-rose-200" : "bg-emerald-50 text-emerald-700 border border-emerald-200"
                              }`}
                            >
                              Tasa hoy: {pct(p.tasa_vigente)}
                            </span>
                          )
                        ) : (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600">Tasa fija {pct(p.tasa_interes)}</span>
                        )}
                      </div>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Préstamo #{p.id} · Fecha: {formatDate(p.fecha_prestamo)} · Cuotas: {p.cuotas_pagadas}/{p.numero_cuotas}
                        {esReparto(p) ? " · Interés sobre capital pendiente" : esMora(p) ? " · 7 % a tiempo / 10 % con retraso" : ""}
                      </p>
                      {abierto && (
                        <p className="text-xs mt-1 flex items-center gap-1.5 flex-wrap">
                          {p.cuotas_atrasadas > 0 ? (
                            <span className="inline-flex items-center gap-1 font-bold text-rose-700">
                              <AlertTriangle className="w-3.5 h-3.5" />
                              {p.cuotas_atrasadas} {p.cuotas_atrasadas === 1 ? "cuota atrasada" : "cuotas atrasadas"}
                            </span>
                          ) : p.estado === "EN_MORA" ? (
                            <span className="inline-flex items-center gap-1 font-bold text-rose-700">
                              <AlertTriangle className="w-3.5 h-3.5" />
                              Venció el {formatDate(p.fecha_vencimiento)}
                            </span>
                          ) : null}
                          {p.fecha_proxima_cuota && (
                            <span className="text-slate-500">
                              {p.cuotas_atrasadas > 0 || p.estado === "EN_MORA" ? "· " : ""}Fecha límite: <strong className="text-slate-700">{formatDate(p.fecha_proxima_cuota)}</strong>
                            </span>
                          )}
                          {num(p.intereses_pendientes) > 0 && (
                            <span className="text-rose-700 font-semibold">· Intereses pendientes: {formatMoney(p.intereses_pendientes)}</span>
                          )}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <p className="text-xs text-slate-400">Total pendiente</p>
                        <p className="font-black text-purple-700 text-lg">{formatMoney(getTotalPendiente(p))}</p>
                        <p className="text-[11px] text-slate-400">Total inicial: {formatMoney(getTotalInicial(p))}</p>
                      </div>
                      <div className="flex flex-col gap-1">
                        {abierto && (
                          <button
                            onClick={() => setListaAbonosId(p.id)}
                            className="px-3 py-1.5 bg-purple-100 hover:bg-purple-200 text-purple-800 text-xs font-bold rounded-lg transition-colors"
                          >
                            Abonar
                          </button>
                        )}
                        <button
                          onClick={() => setExpandedId(expandedId === p.id ? null : p.id)}
                          className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs font-bold rounded-lg transition-colors flex items-center gap-1 justify-center"
                        >
                          Detalle
                          {expandedId === p.id ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                        </button>
                        <button
                          onClick={() => handleDeletePrestamo(p)}
                          disabled={getTotalPendiente(p) > 0}
                          title="Eliminar préstamo"
                          aria-label={`Eliminar préstamo ${p.id}`}
                          className="px-3 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 text-xs font-bold rounded-lg transition-colors flex items-center gap-1 justify-center disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-rose-50"
                        >
                          <Trash2 className="w-3 h-3" />
                          Eliminar
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Detalle expandible */}
                  {expandedId === p.id && (
                    <div className="mt-3 pl-4 border-l-2 border-purple-100 space-y-3">
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 text-xs">
                        <div className="p-2 bg-slate-50 rounded-lg">
                          <p className="text-slate-400">Capital inicial</p>
                          <p className="font-bold text-slate-700">{formatMoney(getCapitalPendiente(p))}</p>
                          <p className="text-[11px] text-slate-400">Pendiente</p>
                        </div>
                        <div className="p-2 bg-purple-50 rounded-lg">
                          <p className="text-purple-500">
                            {esReparto(p)
                              ? `Intereses (10 % x ${p.periodos?.length || 0} ${p.periodos?.length === 1 ? "mes" : "meses"})`
                              : esMora(p) ? `Intereses (7 % / 10 % x ${p.numero_cuotas} meses)` : `Intereses (${p.tasa_interes}% x ${p.numero_cuotas} meses)`}
                          </p>
                          <p className="font-bold text-purple-700">{formatMoney(getInteresesPendientes(p))}</p>
                          <p className="text-[11px] text-purple-400">Pendientes</p>
                        </div>
                        <div className="p-2 bg-amber-50 rounded-lg">
                          <p className="text-amber-600">Capital abonado</p>
                          <p className="font-bold text-amber-700">{formatMoney(getCapitalAbonado(p))}</p>
                          <p className="text-[11px] text-amber-500">
                            de {formatMoney(p.monto_prestado)}
                          </p>
                        </div>
                        <div className="p-2 bg-emerald-50 rounded-lg">
                          <p className="text-emerald-600">Interés abonado</p>
                          <p className="font-bold text-emerald-700">{formatMoney(getInteresesAbonados(p))}</p>
                          <p className="text-[11px] text-emerald-500">de {formatMoney(p.total_intereses)}</p>
                        </div>
                      </div>

                      {esMora(p) && p.periodos?.length > 0 && (
                        <div className="overflow-x-auto">
                          <table className="w-full text-xs min-w-[560px]">
                            <thead>
                              <tr className="text-left text-slate-400 border-b border-slate-100">
                                <th className="py-1.5 pr-2 font-semibold">Cuota</th>
                                <th className="py-1.5 pr-2 font-semibold">Fecha límite</th>
                                {esReparto(p) && <th className="py-1.5 pr-2 font-semibold text-right">Capital del mes</th>}
                                <th className="py-1.5 pr-2 font-semibold">Tasa</th>
                                <th className="py-1.5 pr-2 font-semibold text-right">Interés</th>
                                <th className="py-1.5 pr-2 font-semibold text-right">Pagado</th>
                                <th className="py-1.5 pr-2 font-semibold text-right">Pendiente</th>
                                <th className="py-1.5 pr-2 font-semibold">Estado</th>
                                <th className="py-1.5 font-semibold">Destino</th>
                              </tr>
                            </thead>
                            <tbody>
                              {p.periodos.map((m) => (
                                <tr key={m.numero_cuota} className="border-b border-slate-50 last:border-0 text-slate-600">
                                  <td className="py-1.5 pr-2 font-bold text-slate-700">#{m.numero_cuota}</td>
                                  <td className="py-1.5 pr-2">{formatDate(m.fecha_limite)}</td>
                                  {esReparto(p) && <td className="py-1.5 pr-2 text-right">{formatMoney(m.base)}</td>}
                                  <td className={`py-1.5 pr-2 font-bold ${num(m.tasa) > num(p.tasa_interes) ? "text-rose-700" : "text-emerald-700"}`}>{pct(m.tasa)}</td>
                                  <td className="py-1.5 pr-2 text-right">{formatMoney(m.valor)}</td>
                                  <td className="py-1.5 pr-2 text-right">{formatMoney(m.pagado)}</td>
                                  <td className="py-1.5 pr-2 text-right font-semibold">{formatMoney(m.pendiente)}</td>
                                  <td className="py-1.5 pr-2">
                                    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold ${estadoColor(m.estado)}`}>
                                      {m.estado === "PAGADO" ? <CheckCircle2 className="w-3 h-3" /> : m.estado === "EN_MORA" ? <AlertTriangle className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                                      {m.estado === "PENDIENTE" ? "En plazo" : ESTADO_TEXTO[m.estado]}
                                    </span>
                                  </td>
                                  <td className="py-1.5 text-slate-500">
                                    {m.destino === "REPARTO_7_3"
                                      ? `Socio ${formatMoney(m.interes_socio)} · B. común ${formatMoney(m.interes_bien_comun)}`
                                      : m.destino === "BIEN_COMUN" ? "Bien común" : "Ahorro personal"}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}

                      {p.abonos && p.abonos.length > 0 ? (
                        <div className="space-y-1.5">
                          {p.abonos.map((ab) => (
                            <div key={ab.id} className="flex items-center justify-between gap-2 flex-wrap text-xs text-slate-600 py-1.5 border-b border-slate-50 last:border-0">
                              <span className="flex items-center gap-1.5 flex-wrap">
                                Cuota #{ab.numero_cuota} · {formatDate(ab.fecha_pago)}
                                {ab.tasa_aplicada != null && (
                                  <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold ${num(ab.tasa_aplicada) > num(p.tasa_interes) ? "bg-rose-50 text-rose-700" : "bg-emerald-50 text-emerald-700"}`}>
                                    {pct(ab.tasa_aplicada)}
                                  </span>
                                )}
                                {ab.dias_retraso > 0 && (
                                  <span className="text-[10px] text-rose-600">{ab.dias_retraso} {ab.dias_retraso === 1 ? "día" : "días"} de retraso</span>
                                )}
                              </span>
                              <div className="text-right">
                                <span className="font-bold text-slate-800">{formatMoney(ab.monto_abonado)}</span>
                                <span className="text-slate-400 ml-2">(Capital: {formatMoney(ab.monto_capital)} + Int: {formatMoney(ab.monto_interes)})</span>
                                {ab.interes_bien_comun != null && num(ab.monto_interes) > 0 && (
                                  <span className="block text-[10px] text-slate-400">
                                    Interés → socio {formatMoney(ab.interes_socio)} · bien común {formatMoney(ab.interes_bien_comun)}
                                  </span>
                                )}
                                <button
                                  type="button"
                                  onClick={() => openEditAbono(p, ab)}
                                  title="Editar abono"
                                  aria-label={`Editar abono ${ab.id}`}
                                  className="ml-2 inline-flex p-1 text-slate-400 hover:text-purple-600 hover:bg-purple-50 rounded transition-colors"
                                >
                                  <Edit className="w-3 h-3" />
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-slate-400 italic py-1">Sin abonos registrados aún.</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="py-16 text-center text-slate-400 text-sm">
            {prestamos.length > 0 ? "No hay préstamos con este estado." : "No hay préstamos registrados."}
          </div>
        )}
      </div>
      </>
      )}

      {/* Modal Nuevo Préstamo */}
      <Modal isOpen={isPrestamoModalOpen} onClose={() => setIsPrestamoModalOpen(false)} title="Registrar Nuevo Préstamo">
        <form onSubmit={handleCreatePrestamo} className="space-y-4">
          <div>
            <label className={labelClass}>Socio *</label>
            <select required value={prestamoForm.socio_id} onChange={(e) => setPrestamoForm({ ...prestamoForm, socio_id: e.target.value })}
              className={inputClass}>
              <option value="">Seleccionar socio...</option>
              {socios.filter(s => s.is_active).map(s => (
                <option key={s.id} value={s.id}>{s.nombre} (CC: {s.cedula})</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>Monto a Prestar ($) *</label>
              <MoneyInput required value={prestamoForm.monto_prestado}
                onChange={(e) => setPrestamoForm({ ...prestamoForm, monto_prestado: e.target.value })}
                placeholder="Ej. 500.000"
                className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Interés mensual</label>
              <p className={`${inputClass} bg-slate-50 text-slate-700 font-semibold`}>10 % (7 % socio · 3 % bien común)</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>Número de Cuotas *</label>
              <input type="number" min="1" required value={prestamoForm.numero_cuotas}
                onChange={(e) => setPrestamoForm({ ...prestamoForm, numero_cuotas: e.target.value })}
                className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Fecha de Desembolso</label>
              <input type="date" value={prestamoForm.fecha_prestamo}
                onChange={(e) => setPrestamoForm({ ...prestamoForm, fecha_prestamo: e.target.value })}
                className={inputClass} />
            </div>
          </div>
          {prestamoForm.monto_prestado && (prestamoForm.regla_interes === REGLA_REPARTO ? (
            <div className="p-3 bg-purple-50 rounded-xl border border-purple-100 text-xs text-purple-800 space-y-0.5">
              <p className="font-bold">Estimación del primer mes:</p>
              <p>Interés total (10 %): <strong>{formatMoney(num(prestamoForm.monto_prestado) * 0.10)}</strong></p>
              <p>Ganancia para el socio (7 %): <strong>{formatMoney(num(prestamoForm.monto_prestado) * 0.07)}</strong></p>
              <p>Ganancia para el bien común (3 %): <strong>{formatMoney(num(prestamoForm.monto_prestado) * 0.03)}</strong></p>
              <p className="text-[11px] text-purple-600 pt-1">
                Cada mes el 10 % se calcula sobre el capital pendiente y se sigue cobrando mientras quede capital por pagar.
                La fecha límite de cada cuota es el mismo día del mes del desembolso.
              </p>
            </div>
          ) : prestamoForm.regla_interes === REGLA_MORA ? (
            <div className="p-3 bg-purple-50 rounded-xl border border-purple-100 text-xs text-purple-800 space-y-0.5">
              <p className="font-bold">Estimación mensual:</p>
              <p>Pagando a tiempo (7 %): <strong>{formatMoney(num(prestamoForm.monto_prestado) * 0.07)}</strong></p>
              <p>Pagando con retraso (10 %): <strong>{formatMoney(num(prestamoForm.monto_prestado) * 0.10)}</strong></p>
            </div>
          ) : prestamoForm.tasa_interes && (
            <div className="p-3 bg-purple-50 rounded-xl border border-purple-100 text-xs text-purple-800">
              <p className="font-bold">Estimación:</p>
              <p>Interés mensual: <strong>{formatMoney(parseFloat(prestamoForm.monto_prestado) * parseFloat(prestamoForm.tasa_interes) / 100)}</strong></p>
              <p>Intereses proyectados ({prestamoForm.numero_cuotas} meses): <strong>{formatMoney(parseFloat(prestamoForm.monto_prestado) * parseFloat(prestamoForm.tasa_interes) / 100 * parseInt(prestamoForm.numero_cuotas || 0, 10))}</strong></p>
            </div>
          ))}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => setIsPrestamoModalOpen(false)} className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl">Cancelar</button>
            <button type="submit" disabled={submittingPrestamo} className="px-5 py-2 bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold rounded-xl disabled:opacity-50">
              {submittingPrestamo ? "Registrando..." : "Registrar Préstamo"}
            </button>
          </div>
        </form>
      </Modal>

      {/* Modal Abonar en estilo lista */}
      <Modal
        isOpen={Boolean(prestamoLista)}
        onClose={() => setListaAbonosId(null)}
        maxWidth="max-w-4xl"
        title={prestamoLista ? `Abonar — Préstamo #${prestamoLista.id} — ${getSocioNombre(prestamoLista.socio_id)}` : "Abonar"}
      >
        {prestamoLista && (
          <div className="space-y-3">
            <p className="text-xs text-slate-500">
              Saldo de capital <strong className="text-slate-700">{formatMoney(getCapitalPendiente(prestamoLista))}</strong> ·
              Total pendiente <strong className="text-purple-700">{formatMoney(getTotalPendiente(prestamoLista))}</strong>.
              Escribe capital, interés y fecha en la línea nueva y tócala para registrar el abono.
            </p>
            <AbonosLineas
              prestamo={prestamoLista}
              lineaInicial
              onRegistrado={fetchAll}
              onEditar={(ab) => { setListaAbonosId(null); openEditAbono(prestamoLista, ab); }}
            />
          </div>
        )}
      </Modal>

      {/* Modal Abonar Cuota */}
      <Modal
        isOpen={isAbonoModalOpen}
        onClose={cerrarAbono}
        title={selectedPrestamo
          ? esMora(selectedPrestamo)
            ? `${editingAbono ? "Editar abono" : "Abonar"} — Préstamo #${selectedPrestamo.id}`
            : `${editingAbono ? "Editar" : "Abonar"} Cuota #${editingAbono?.numero_cuota || selectedPrestamo.cuotas_pagadas + 1} — Préstamo #${selectedPrestamo.id}`
          : "Abonar Cuota"}
      >
        {selectedPrestamo && esMora(selectedPrestamo) ? (
          <form onSubmit={handleAbono} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelClass}>Fecha del pago *</label>
                {/* Al cambiar la fecha la cuota se vuelve a elegir sola: si la fecha cae
                    después de la última cuota, aparece la siguiente automáticamente. */}
                <input type="date" required value={abonoForm.fecha_pago}
                  onChange={(e) => { autoCompletar.current = true; setAbonoForm({ ...abonoForm, fecha_pago: e.target.value, numero_cuota: "" }); }}
                  className={inputClass} />
              </div>
              <div>
                <label className={labelClass}>Cuota *</label>
                <select value={abonoForm.numero_cuota} onChange={(e) => setAbonoForm({ ...abonoForm, numero_cuota: e.target.value })}
                  className={inputClass}>
                  {(vistaAbono?.cuotas?.length
                    ? vistaAbono.cuotas
                    : abonoForm.numero_cuota ? [{ numero_cuota: Number(abonoForm.numero_cuota) }] : []
                  ).map((c) => (
                    <option key={c.numero_cuota} value={c.numero_cuota}>
                      #{c.numero_cuota}
                      {c.fecha_limite ? ` · vence ${formatDate(c.fecha_limite)}` : ""}
                      {c.nueva ? " · nueva" : c.pagada ? " · pagada" : ""}
                    </option>
                  ))}
                </select>
                {vistaAbono?.cuota_nueva && (
                  <p className="text-[11px] text-purple-700 font-semibold mt-1">
                    Se agregó la cuota #{vistaAbono.cuota_nueva} (vence{" "}
                    {formatDate(vistaAbono.cuotas.find((c) => c.nueva)?.fecha_limite)}) por la fecha del pago.
                  </p>
                )}
              </div>
            </div>

            {errorVistaAbono && (
              <p className="p-3 rounded-xl bg-rose-50 border border-rose-100 text-xs text-rose-700">{errorVistaAbono}</p>
            )}

            {vistaAbono && (
              <div className={`p-3 rounded-xl border text-xs space-y-1 ${vistaAbono.dias_retraso > 0 ? "bg-rose-50 border-rose-100 text-rose-900" : "bg-emerald-50 border-emerald-100 text-emerald-900"}`}>
                <p className="font-bold flex items-center gap-1.5">
                  {vistaAbono.dias_retraso > 0 ? <AlertTriangle className="w-3.5 h-3.5" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                  {esReparto(selectedPrestamo) ? `Tasa: ${pct(vistaAbono.tasa_sugerida)}` : `Tasa sugerida: ${pct(vistaAbono.tasa_sugerida)}`}
                </p>
                <p>Fecha límite de la cuota #{vistaAbono.numero_cuota}: <strong>{formatDate(vistaAbono.fecha_limite)}</strong> · Pago: <strong>{formatDate(vistaAbono.fecha_pago)}</strong></p>
                <p>{vistaAbono.motivo}.</p>
                {num(vistaAbono.interes_pagado) > 0 && (
                  <p>Ya pagado en esta cuota: <strong>{formatMoney(vistaAbono.interes_pagado)}</strong>{vistaAbono.tasa_elegida_previa ? ` (al ${pct(vistaAbono.tasa_elegida_previa)})` : ""}</p>
                )}
                {esReparto(selectedPrestamo) && (
                  <p>
                    Capital del mes: <strong>{formatMoney(vistaAbono.capital_base)}</strong> · Interés del mes: <strong>{formatMoney(vistaAbono.interes_tasa_normal)}</strong>
                    {" "}(socio {formatMoney(vistaAbono.interes_socio)} · bien común {formatMoney(vistaAbono.interes_bien_comun)})
                  </p>
                )}
                <p className="flex items-center gap-1"><Info className="w-3 h-3" /> Destino del interés: {DESTINO_TEXTO[vistaAbono.destino]}</p>
              </div>
            )}

            {vistaAbono && !esReparto(selectedPrestamo) && (
              <div>
                <p className={labelClass}>Tasa a aplicar *</p>
                <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Tasa a aplicar">
                  {[
                    { tasa: vistaAbono.tasa_normal, titulo: "A tiempo", valor: vistaAbono.interes_tasa_normal, pendiente: vistaAbono.pendiente_tasa_normal },
                    { tasa: vistaAbono.tasa_mora, titulo: "Con retraso", valor: vistaAbono.interes_tasa_mora, pendiente: vistaAbono.pendiente_tasa_mora },
                  ].map((op) => {
                    const activa = tasaElegida === num(op.tasa);
                    const sugerida = num(op.tasa) === num(vistaAbono.tasa_sugerida);
                    return (
                      <button
                        key={op.titulo}
                        type="button"
                        role="radio"
                        aria-checked={activa}
                        onClick={() => elegirTasa(op.tasa)}
                        className={`p-3 rounded-xl border-2 text-left transition-colors ${
                          activa ? "border-purple-500 bg-purple-50" : "border-slate-200 hover:border-purple-200"
                        }`}
                      >
                        <p className="text-lg font-black text-slate-800">{pct(op.tasa)}</p>
                        <p className="text-[11px] text-slate-500">{op.titulo} · {formatMoney(op.valor)} / mes</p>
                        <p className="text-[11px] text-slate-500">Pendiente: <strong>{formatMoney(op.pendiente)}</strong></p>
                        {sugerida && <p className="mt-1 text-[10px] font-bold text-purple-700 uppercase">Sugerida</p>}
                      </button>
                    );
                  })}
                </div>
                {tasaManual && (
                  <p className="mt-2 text-[11px] text-amber-700 bg-amber-50 border border-amber-100 rounded-lg p-2">
                    Elegiste {pct(tasaElegida)} aunque por la fecha corresponde {pct(vistaAbono.tasa_sugerida)}. Quedará registrado en el abono.
                  </p>
                )}
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelClass}>Interés ($)</label>
                <MoneyInput value={abonoForm.monto_interes}
                  onChange={(e) => setAbonoForm({ ...abonoForm, monto_interes: e.target.value })}
                  className={inputClass} />
                {vistaAbono && abonoForm.tasa_aplicada && (
                  <p className="text-[11px] text-slate-400 mt-1">Máximo {formatMoney(pendienteSegunTasa(abonoForm.tasa_aplicada))} para esta cuota</p>
                )}
              </div>
              <div>
                <label className={labelClass}>Capital ($)</label>
                <MoneyInput value={abonoForm.monto_capital}
                  onChange={(e) => setAbonoForm({ ...abonoForm, monto_capital: e.target.value })}
                  placeholder="0"
                  className={inputClass} />
                {vistaAbono && <p className="text-[11px] text-slate-400 mt-1">Saldo de capital: {formatMoney(vistaAbono.saldo_capital)}</p>}
              </div>
            </div>
            <div className="p-3 bg-slate-50 rounded-xl text-sm flex items-center justify-between">
              <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Total del abono</span>
              <span className="font-black text-purple-700">{formatMoney(num(abonoForm.monto_capital) + num(abonoForm.monto_interes))}</span>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={cerrarAbono} className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl">Cancelar</button>
              <button type="submit" disabled={submittingAbono || !vistaAbono} className="px-5 py-2 bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold rounded-xl disabled:opacity-50">
                {submittingAbono ? "Guardando..." : editingAbono ? "Guardar cambios" : `Registrar abono${abonoForm.tasa_aplicada ? ` al ${pct(abonoForm.tasa_aplicada)}` : ""}`}
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={handleAbono} className="space-y-4">
            {selectedPrestamo && (
              <div className="p-3 bg-purple-50 rounded-xl text-xs text-purple-800 border border-purple-100">
                <p>Saldo pendiente: <strong>{formatMoney(selectedPrestamo.saldo_pendiente)}</strong></p>
                <p className="mt-0.5">Tasa fija: {selectedPrestamo.tasa_interes}% · Cuota siguiente: #{selectedPrestamo.cuotas_pagadas + 1} de {selectedPrestamo.numero_cuotas}</p>
              </div>
            )}
            <div>
              <label className={labelClass}>Monto Total a Abonar ($) *</label>
              <MoneyInput required value={abonoForm.monto_abonado}
                onChange={(e) => setAbonoForm({ ...abonoForm, monto_abonado: e.target.value })}
                placeholder="Ej. 150.000"
                className={inputClass} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelClass}>Capital Amortizado ($) *</label>
                <MoneyInput required value={abonoForm.monto_capital}
                  onChange={(e) => setAbonoForm({ ...abonoForm, monto_capital: e.target.value })}
                  placeholder="Ej. 125.000"
                  className={inputClass} />
              </div>
              <div>
                <label className={labelClass}>Interés Cobrado ($)</label>
                <MoneyInput value={abonoForm.monto_interes}
                  onChange={(e) => setAbonoForm({ ...abonoForm, monto_interes: e.target.value })}
                  placeholder="Ej. 25.000"
                  className={inputClass} />
              </div>
            </div>
            <div>
              <label className={labelClass}>Fecha *</label>
              <input
                type="date"
                required
                value={abonoForm.fecha_pago}
                onChange={(e) => setAbonoForm({ ...abonoForm, fecha_pago: e.target.value })}
                className={inputClass}
              />
              <p className="text-[11px] text-slate-400 mt-1">Día en que se realizó el pago (puede ser anterior, de hoy o futuro).</p>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={cerrarAbono} className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl">Cancelar</button>
              <button type="submit" disabled={submittingAbono} className="px-5 py-2 bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold rounded-xl disabled:opacity-50">
                {submittingAbono ? "Guardando..." : editingAbono ? "Guardar cambios" : "Registrar Abono"}
              </button>
            </div>
          </form>
        )}
      </Modal>

    </div>
  );
};
