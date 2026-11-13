import React, { useState, useEffect } from "react";
import { 
  Users, 
  Search, 
  UserPlus, 
  Phone, 
  MapPin, 
  CreditCard, 
  DollarSign, 
  Eye, 
  Edit, 
  PlusCircle, 
  AlertCircle,
  FileText,
  BadgeCheck,
  Trash2
} from "lucide-react";
import api from "../api/client";
import { Modal } from "../components/Modal";
import { MoneyInput } from "../components/MoneyInput";
import { RichTextDisplay, RichTextField } from "../components/RichTextField";
import {
  ActividadesSocio, AportesMensuales, DeduccionesSocio, DeudasCredito, MultasSocio,
} from "../components/SocioAportesMultas";
import { formatMoney, formatDate, fechaLocalISO } from "../utils/formatters";

const ACCIONES_MOVIMIENTO = {
  APORTE: "Aporte",
  MULTA: "Multa",
  PAGO_MULTA: "Pago de multa",
  RETIRO_AHORRO: "Retiro de ahorro",
  ABONO_PRESTAMO: "Abono a préstamo",
  PAGO_PRESTAMO: "Pago de préstamo",
  CORRECCION_ABONO: "Corrección de abono",
  REVERSION_ABONO: "Reversión de abono",
};

// Movimientos de préstamos (calculados en el servidor) con la forma del historial del socio.
const TIPO_MOV_PRESTAMO = {
  ABONO: "ABONO_PRESTAMO",
  PAGO: "PAGO_PRESTAMO",
  EDICION: "CORRECCION_ABONO",
  REVERSION: "REVERSION_ABONO",
};
const TIPO_MOV_PRESTAMO_VALORES = Object.values(TIPO_MOV_PRESTAMO);
const movimientosDePrestamos = (perfil) =>
  (perfil?.movimientos_prestamos || []).map((m) => ({
    id: m.clave,
    tipo_movimiento: TIPO_MOV_PRESTAMO[m.tipo] || m.tipo,
    descripcion: m.descripcion,
    fecha: m.fecha,
    monto: m.monto,
    anulado: !m.vigente,
  }));

const MESES_HOJA = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

const escaparHtml = (texto) =>
  String(texto ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Valores como en la hoja de cálculo: vacío o "$ -" cuando es cero.
const celdaDinero = (valor, guion = false) => {
  const n = Number(valor || 0);
  if (!n) return guion ? "$ -" : "";
  return escaparHtml(formatMoney(n).replace(/\s/g, " "));
};

// Colores tomados del logo de la natillera.
const HOJA_ESTILOS = `
  @page { size: landscape; margin: 10mm; }
  * { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  :root { --cafe: #3b1a14; --cafe-suave: #5a2d22; --crema: #f7f4ec; --beige: #e7e2d6; --oro: #8b6a25; --linea: #d8d1c2; --rosa: #f6e3dc; }
  body { font-family: "Segoe UI", Arial, Helvetica, sans-serif; color: var(--cafe); margin: 0; padding: 18px 22px; background: #fff; }
  .marca { position: fixed; top: 50%; left: 50%; width: 118mm; transform: translate(-50%, -50%); opacity: .09; z-index: 0; pointer-events: none; }
  .contenido { position: relative; z-index: 1; }
  header { display: flex; align-items: center; gap: 16px; padding-bottom: 12px; border-bottom: 3px solid var(--cafe); margin-bottom: 14px; }
  header img { width: 64px; height: 64px; border-radius: 50%; object-fit: cover; }
  header .marca-texto { flex: 1; }
  header .natillera { font-size: 11px; font-weight: 800; letter-spacing: .18em; text-transform: uppercase; color: var(--oro); }
  header h1 { margin: 2px 0 0; font-size: 24px; font-weight: 900; letter-spacing: .02em; text-transform: uppercase; }
  header .lema { font-size: 11px; color: var(--cafe-suave); font-style: italic; }
  header .chip { text-align: right; font-size: 11px; color: var(--cafe-suave); line-height: 1.5; }
  header .chip b { display: inline-block; background: var(--cafe); color: var(--crema); padding: 3px 12px; border-radius: 999px; font-size: 13px; margin-bottom: 4px; }
  .fila { display: flex; gap: 14px; align-items: flex-start; }
  .tarjeta { border: 1px solid var(--linea); border-radius: 12px; overflow: hidden; background: rgba(255,255,255,.82); }
  table { border-collapse: collapse; width: 100%; font-size: 11.5px; }
  th { background: var(--cafe); color: var(--crema); font-size: 10px; letter-spacing: .08em; text-transform: uppercase; text-align: left; padding: 6px 8px; font-weight: 700; }
  td { padding: 4px 8px; border-bottom: 1px solid var(--linea); height: 22px; vertical-align: middle; word-break: break-word; }
  td.sep, th.sep { border-left: 2px solid var(--beige); }
  /* Línea divisoria fina entre Cuota y R. interna. */
  td.div, th.div { border-left: 1px solid var(--linea); }
  th.div { border-left-color: rgba(247,244,236,.35); }
  tbody tr:nth-child(even) td { background: rgba(231,226,214,.35); }
  .num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
  .mes { font-weight: 700; }
  .cant { color: var(--oro); font-size: 10px; font-weight: 700; }
  td.gasto { background: var(--rosa) !important; }
  tfoot td { background: var(--beige); font-weight: 800; border-bottom: 0; border-top: 2px solid var(--cafe); }
  .principal { flex: 1; }
  .lateral { width: 27%; display: flex; flex-direction: column; gap: 14px; }
  .lateral h3 { margin: 0; padding: 7px 10px; background: var(--oro); color: #fff; font-size: 11px; letter-spacing: .1em; text-transform: uppercase; }
  .resumen td { font-size: 11px; }
  .total-ahorrado { background: var(--cafe); color: var(--crema); padding: 12px 14px; border-radius: 12px; }
  .total-ahorrado small { display: block; font-size: 10px; letter-spacing: .14em; text-transform: uppercase; color: #e9d9b5; }
  .total-ahorrado strong { display: block; font-size: 24px; font-weight: 900; margin-top: 2px; }
  .vacio { color: #a39785; font-style: italic; text-align: center; padding: 10px; }
  footer { margin-top: 12px; font-size: 9.5px; color: var(--cafe-suave); display: flex; justify-content: space-between; gap: 12px; }
`;

const construirHoja = (h, logoUrl) => {
  const meses = h.meses.map((m) => ({ etiqueta: MESES_HOJA[m.mes - 1], cuota: m.cuota, rifa: m.rifa_interna }));
  if (Number(h.otros_aportes)) {
    meses.push({ etiqueta: "Otros años", cuota: h.otros_aportes, rifa: 0 });
  }
  const actividades = h.actividades;
  const deducciones = h.deducciones;
  const filas = Math.max(meses.length, actividades.length, deducciones.length);
  const DEUDAS = 3; // Préstamos, intereses y multas; el resto son gastos generales.
  const suma = (lista, campo) => lista.reduce((t, x) => t + Number(x[campo] || 0), 0);

  let cuerpo = "";
  for (let i = 0; i < filas; i += 1) {
    const m = meses[i];
    const a = actividades[i];
    const d = deducciones[i];
    const cantidad = a && a.cantidad_vendida != null ? ` <span class="cant">· ${escaparHtml(a.cantidad_vendida)} und.</span>` : "";
    cuerpo += `<tr>
      <td class="mes">${m ? escaparHtml(m.etiqueta) : ""}</td>
      <td class="num">${m ? celdaDinero(m.cuota) : ""}</td>
      <td class="num div">${m ? celdaDinero(m.rifa) : ""}</td>
      <td class="sep">${a ? escaparHtml(a.nombre) + cantidad : ""}</td>
      <td class="num">${a ? celdaDinero(a.ganancia, true) : ""}</td>
      <td class="sep">${d ? escaparHtml(d.concepto) : ""}</td>
      <td class="num ${d && i >= DEUDAS ? "gasto" : ""}">${d ? celdaDinero(d.valor, true) : ""}</td>
    </tr>`;
  }

  const t = h.total_ahorrado;
  const resumen = [
    ["Aportes mensuales", suma(meses, "cuota")],
    ...(Number(h.retiros) ? [["Retiros de ahorro", -Number(h.retiros)]] : []),
    ["Ganancias por intereses", t.ganancias_intereses],
    ["Ganancias en actividades", t.ganancias_actividades],
    ["Ganancias en rifa interna", t.ganancias_rifa_interna],
    ["Ganancias en rifas (grandes y pequeñas)", t.ganancias_rifas],
    ["Ganancias en reuniones", t.ganancias_reuniones],
    ["Participación en el bien común", t.bien_comun],
  ].map(([texto, valor]) => `<tr><td>${escaparHtml(texto)}</td><td class="num">${celdaDinero(valor, true)}</td></tr>`).join("");

  return `<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>${escaparHtml(h.socio.nombre)} - Total ahorrado ${escaparHtml(h.anio)}</title>
<style>${HOJA_ESTILOS}</style></head><body>
<img class="marca" src="${escaparHtml(logoUrl)}" alt="">
<div class="contenido">
  <header>
    <img src="${escaparHtml(logoUrl)}" alt="Natillera Puerto Berrío">
    <div class="marca-texto">
      <div class="natillera">Natillera Puerto Berrío</div>
      <h1>${escaparHtml(h.socio.nombre)}</h1>
      <div class="lema">Ahorra con ¡propósito!</div>
    </div>
    <div class="chip"><b>Año ${escaparHtml(h.anio)}</b><br>C.C. ${escaparHtml(h.socio.cedula)} · ID ${escaparHtml(h.socio.id)}${h.socio.activo ? "" : "<br>Socio inactivo"}</div>
  </header>

  <div class="fila">
    <div class="tarjeta principal">
      <table>
        <thead><tr>
          <th>Mes</th><th class="num">Cuota</th><th class="num div">R. interna</th>
          <th class="sep">Actividad</th><th class="num">Ganancia</th>
          <th class="sep">Deducciones</th><th class="num">Valor</th>
        </tr></thead>
        <tbody>${cuerpo}</tbody>
        <tfoot><tr>
          <td>Total</td><td class="num">${celdaDinero(suma(meses, "cuota"), true)}</td><td class="num div">${celdaDinero(suma(meses, "rifa"), true)}</td>
          <td class="sep">Total actividades</td><td class="num">${celdaDinero(suma(actividades, "ganancia"), true)}</td>
          <td class="sep">Gastos total</td><td class="num">${celdaDinero(h.total_deducciones, true)}</td>
        </tr></tfoot>
      </table>
    </div>

    <div class="lateral">
      <div class="tarjeta resumen">
        <h3>Total ahorrado</h3>
        <table><tbody>${resumen}</tbody></table>
      </div>
      <div class="total-ahorrado"><small>Total ahorrado</small><strong>${celdaDinero(t.total, true)}</strong></div>
    </div>
  </div>

  <footer>
    <span>Gastos generales repartidos en partes iguales entre los socios activos; rifas grandes y pequeñas y reuniones según el ahorro de cada socio activo.</span>
    <span>Generado el ${escaparHtml(new Date().toLocaleString("es-CO"))}</span>
  </footer>
</div>
</body></html>`;
};

// Hoja imprimible (o PDF desde el diálogo de impresión) con el estilo de la planilla y el logo de la natillera.
const imprimirTotalAhorrado = async (perfil) => {
  // La ventana se abre antes de pedir los datos para que el navegador no la bloquee.
  const ventana = window.open("", "_blank", "width=1200,height=850");
  if (!ventana) {
    alert("El navegador bloqueó la ventana de impresión. Permite las ventanas emergentes e inténtalo de nuevo.");
    return;
  }
  ventana.document.write('<p style="font-family:Arial;padding:24px;color:#3b1a14">Preparando la hoja...</p>');
  try {
    const { data } = await api.get(`/socios/${perfil.id}/hoja-ahorro`);
    ventana.document.open();
    ventana.document.write(construirHoja(data, `${window.location.origin}/logo-natillera.jpg`));
    ventana.document.close();
    // Esperar el logo para que salga en la impresión.
    await Promise.all([...ventana.document.images].map((img) => (
      img.complete ? null : new Promise((listo) => { img.onload = listo; img.onerror = listo; })
    )));
    ventana.focus();
    ventana.print();
  } catch (err) {
    console.error(err);
    ventana.close();
    alert(err.response?.data?.detail || "No se pudo preparar la hoja para imprimir.");
  }
};

// Formulario de socio: los campos numéricos descartan cualquier letra al escribir o pegar.
const soloDigitos = (valor) => valor.replace(/\D/g, "");
const soloMonto = (valor) => {
  const limpio = valor.replace(",", ".").replace(/[^\d.]/g, "");
  const [enteros, ...resto] = limpio.split(".");
  return resto.length ? `${enteros}.${resto.join("").slice(0, 2)}` : enteros;
};

const CAMPOS_SOCIO = {
  id: "ID identificativo",
  cedula: "Número de cédula",
  nombre: "Nombre completo",
  telefono: "Teléfono / Celular",
  residencia: "Dirección de residencia",
  aporte_mensual: "Aporte mensual",
};

// Traduce los errores de validación del servidor a mensajes con el nombre del campo.
const mensajeErrorSocio = (err) => {
  const detalle = err.response?.data?.detail;
  if (typeof detalle === "string") return detalle;
  if (!Array.isArray(detalle)) return "Error al guardar el socio.";
  const lineas = detalle.map((d) => {
    const campo = CAMPOS_SOCIO[d.loc?.[d.loc.length - 1]] || "Dato";
    const ctx = d.ctx || {};
    if (d.type === "string_too_short") return `${campo}: debe tener al menos ${ctx.min_length} caracteres.`;
    if (d.type === "string_too_long") return `${campo}: puede tener máximo ${ctx.max_length} caracteres.`;
    if (d.type === "missing") return `${campo}: es obligatorio.`;
    if (/greater_than|less_than/.test(d.type)) return `${campo}: el valor no es válido.`;
    if (/decimal|int|float|number/.test(d.type)) return `${campo}: solo se permiten números.`;
    return `${campo}: ${d.msg}`;
  });
  return `No se pudo guardar el socio:\n\n${lineas.join("\n")}`;
};

export const Socios = () => {
  const [socios, setSocios] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [sortBy, setSortBy] = useState("alfabetico");
  const [loading, setLoading] = useState(true);

  // Modal Crear / Editar Socio
  const [isSocioModalOpen, setIsSocioModalOpen] = useState(false);
  const [editingSocio, setEditingSocio] = useState(null);
  const [formData, setFormData] = useState({
    id: "",
    cedula: "",
    nombre: "",
    telefono: "",
    residencia: "",
    aporte_mensual: "100000.00",
  });
  const [submittingSocio, setSubmittingSocio] = useState(false);
  const [deletingSocioId, setDeletingSocioId] = useState(null);

  // Modal Perfil Financiero / Estado de Cuenta
  const [selectedSocioProfile, setSelectedSocioProfile] = useState(null);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
  const [loadingProfile, setLoadingProfile] = useState(false);

  // Modal Registro de Movimiento (Aporte / Multa)
  const [isMovementModalOpen, setIsMovementModalOpen] = useState(false);
  const [movementData, setMovementData] = useState({
    tipo_movimiento: "MULTA",
    monto: "",
    descripcion: "",
    fecha: fechaLocalISO(),
  });
  const [submittingMovement, setSubmittingMovement] = useState(false);

  // Orden y filtro del historial de movimientos del socio
  const [historialOrden, setHistorialOrden] = useState("fecha_desc");
  const [historialTipo, setHistorialTipo] = useState("TODOS");

  const fetchSocios = async () => {
    try {
      setLoading(true);
      const res = await api.get("/socios");
      setSocios(res.data);
    } catch (err) {
      console.error("Error al cargar socios", err);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteSocio = async (socio) => {
    if (!window.confirm(`¿Deseas eliminar al socio ${socio.nombre}?`)) return;

    try {
      setDeletingSocioId(socio.id);
      await api.delete(`/socios/${socio.id}`);
      await fetchSocios();
    } catch (err) {
      console.error(err);
      alert(err.response?.data?.detail || "Error al eliminar el socio.");
    } finally {
      setDeletingSocioId(null);
    }
  };

  useEffect(() => {
    fetchSocios();
  }, []);

  const openCreateModal = () => {
    setEditingSocio(null);
    const idsUsados = new Set(socios.map((socio) => socio.id));
    let siguienteId = 1;
    while (idsUsados.has(siguienteId)) siguienteId += 1;
    setFormData({
      id: String(siguienteId),
      cedula: "",
      nombre: "",
      telefono: "",
      residencia: "",
      aporte_mensual: "100000.00",
    });
    setIsSocioModalOpen(true);
  };

  const openEditModal = (socio) => {
    setEditingSocio(socio);
    setFormData({
      id: socio.id,
      cedula: socio.cedula,
      nombre: socio.nombre,
      telefono: socio.telefono || "",
      residencia: socio.residencia || "",
      aporte_mensual: socio.aporte_mensual,
    });
    setIsSocioModalOpen(true);
  };

  const handleSaveSocio = async (e) => {
    e.preventDefault();
    try {
      setSubmittingSocio(true);
      if (editingSocio) {
        const nuevoId = Number(formData.id);
        if (nuevoId !== editingSocio.id && !window.confirm(
          `¿Cambiar el ID del socio de ${editingSocio.id} a ${nuevoId}? Sus aportes, multas y préstamos pasarán al nuevo ID.`
        )) return;
        await api.put(`/socios/${editingSocio.id}`, {
          id: nuevoId,
          cedula: formData.cedula,
          nombre: formData.nombre,
          telefono: formData.telefono,
          residencia: formData.residencia,
          aporte_mensual: formData.aporte_mensual,
        });
      } else {
        await api.post("/socios", formData);
      }
      setIsSocioModalOpen(false);
      fetchSocios();
    } catch (err) {
      console.error(err);
      alert(mensajeErrorSocio(err));
    } finally {
      setSubmittingSocio(false);
    }
  };

  const openProfileModal = async (socioId) => {
    try {
      setLoadingProfile(true);
      setIsProfileModalOpen(true);
      const res = await api.get(`/socios/${socioId}/perfil`);
      setSelectedSocioProfile(res.data);
    } catch (err) {
      console.error("Error al obtener perfil", err);
      alert("No se pudo cargar el perfil del socio.");
      setIsProfileModalOpen(false);
    } finally {
      setLoadingProfile(false);
    }
  };

  // Recarga el perfil abierto sin mostrar el indicador de carga (conserva secciones desplegadas).
  const reloadProfile = async () => {
    if (!selectedSocioProfile) return;
    try {
      const res = await api.get(`/socios/${selectedSocioProfile.id}/perfil`);
      setSelectedSocioProfile(res.data);
    } catch (err) {
      console.error("Error al actualizar perfil", err);
    }
  };

  const handleCreateMovement = async (e) => {
    e.preventDefault();
    if (!selectedSocioProfile) return;
    const socioId = selectedSocioProfile.id;
    try {
      setSubmittingMovement(true);
      await api.post(`/socios/${socioId}/movimientos`, {
        tipo_movimiento: "MULTA",
        monto: movementData.monto,
        descripcion: movementData.descripcion || "Registro de multa",
        fecha: movementData.fecha || undefined,
      });
      setIsMovementModalOpen(false);
      setMovementData({ tipo_movimiento: "MULTA", monto: "", descripcion: "", fecha: fechaLocalISO() });
      // Recargar perfil y lista
      await openProfileModal(socioId);
      await fetchSocios();
    } catch (err) {
      console.error(err);
      alert(err.response?.data?.detail || "Error al registrar el movimiento.");
    } finally {
      setSubmittingMovement(false);
    }
  };

  const historialVisible = [
    ...(selectedSocioProfile?.historial_finanzas || []),
    ...movimientosDePrestamos(selectedSocioProfile),
  ]
    .filter((t) => historialTipo === "TODOS" || t.tipo_movimiento === historialTipo)
    .slice()
    .sort((a, b) => {
      const porFecha = new Date(b.fecha) - new Date(a.fecha) || b.id - a.id;
      if (historialOrden === "fecha_asc") return -porFecha;
      if (historialOrden === "accion") {
        const etiqueta = (t) => ACCIONES_MOVIMIENTO[t.tipo_movimiento] || t.tipo_movimiento;
        return etiqueta(a).localeCompare(etiqueta(b), "es") || porFecha;
      }
      return porFecha;
    });

  const normalizedSearch = searchTerm.trim().toLowerCase();
  const exactIdMatches = normalizedSearch
    ? socios.filter((socio) => String(socio.id) === normalizedSearch)
    : [];
  const filteredSocios = (exactIdMatches.length > 0 ? exactIdMatches : socios.filter(
    (s) =>
      s.nombre.toLowerCase().includes(normalizedSearch) ||
      s.cedula.includes(searchTerm) ||
      String(s.id).includes(searchTerm.trim())
  ))
    .slice()
    .sort((a, b) => (
      sortBy === "id"
        ? a.id - b.id
        : a.nombre.localeCompare(b.nombre, "es")
    ));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-black text-slate-800 tracking-tight flex items-center gap-2.5">
            <Users className="w-7 h-7 text-emerald-600" />
            Directorio de Socios
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Administra los miembros, sus datos personales y estados de cuenta.
          </p>
        </div>

        <button
          onClick={openCreateModal}
          className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold rounded-xl shadow-md shadow-emerald-600/20 transition-all active:scale-95"
        >
          <UserPlus className="w-4 h-4" />
          Nuevo Socio
        </button>
      </div>

      {/* Buscador y ordenamiento */}
      <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_220px] gap-3">
        <div className="relative">
          <Search className="w-5 h-5 text-slate-400 absolute left-4 top-3.5" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Buscar socio por nombre, cédula o ID..."
            className="w-full pl-12 pr-4 py-3 bg-white rounded-2xl border border-slate-200/80 focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm shadow-xs"
          />
        </div>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="w-full px-3.5 py-3 bg-white rounded-2xl border border-slate-200/80 focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm font-semibold text-slate-700 shadow-xs"
        >
          <option value="alfabetico">Orden alfabético</option>
          <option value="id">Orden por ID</option>
        </select>
      </div>

      {/* Tabla de Socios */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-16 text-center text-slate-400 text-sm">
            <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
            Cargando socios...
          </div>
        ) : filteredSocios.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50/80 text-xs uppercase font-bold text-slate-500 border-b border-slate-100">
                <tr>
                  <th className="px-6 py-4">ID</th>
                  <th className="px-6 py-4">Socio / Cédula</th>
                  <th className="px-6 py-4">Contacto</th>
                  <th className="px-6 py-4">Aporte Pactado</th>
                  <th className="px-6 py-4">Estado</th>
                  <th className="px-6 py-4 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredSocios.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-6 py-4 font-black text-slate-500">{s.id}</td>
                    <td className="px-6 py-4">
                      <p className="font-bold text-slate-800">{s.nombre}</p>
                      <p className="text-xs text-slate-400">CC: {s.cedula}</p>
                    </td>
                    <td className="px-6 py-4">
                      {s.telefono && (
                        <p className="flex items-center gap-1.5 text-xs text-slate-600">
                          <Phone className="w-3.5 h-3.5 text-slate-400" />
                          {s.telefono}
                        </p>
                      )}
                      {s.residencia && (
                        <p className="flex items-center gap-1.5 text-xs text-slate-400 mt-0.5">
                          <MapPin className="w-3.5 h-3.5 text-slate-400" />
                          {s.residencia}
                        </p>
                      )}
                    </td>
                    <td className="px-6 py-4 font-bold text-slate-700">
                      {formatMoney(s.aporte_mensual)} <span className="text-[11px] font-normal text-slate-400">/ mes</span>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold ${
                        s.is_active ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"
                      }`}>
                        {s.is_active ? "Activo" : "Inactivo"}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right space-x-2">
                      <button
                        onClick={() => openProfileModal(s.id)}
                        className="p-2 text-emerald-600 hover:text-emerald-800 hover:bg-emerald-50 rounded-lg transition-colors"
                        title="Ver Estado de Cuenta"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => openEditModal(s)}
                        className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                        title="Editar Socio"
                      >
                        <Edit className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleDeleteSocio(s)}
                        disabled={deletingSocioId === s.id}
                        className="p-2 text-red-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        title="Eliminar Socio"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-16 text-center text-slate-400 text-sm">
            No se encontraron socios registrados.
          </div>
        )}
      </div>

      {/* Modal Crear / Editar Socio */}
      <Modal
        isOpen={isSocioModalOpen}
        onClose={() => setIsSocioModalOpen(false)}
        title={editingSocio ? "Editar Datos del Socio" : "Registrar Nuevo Socio"}
      >
        <form onSubmit={handleSaveSocio} className="space-y-4">
          <div>
            <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
              ID identificativo *
            </label>
            <input
              type="text"
              inputMode="numeric"
              pattern="[1-9][0-9]*"
              title="ID identificativo: solo números enteros mayores a cero"
              maxLength={9}
              required
              value={formData.id}
              onChange={(e) => setFormData({ ...formData, id: soloDigitos(e.target.value) })}
              placeholder="Ej. 12"
              className="w-full px-3.5 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm disabled:bg-slate-100"
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
              Número de Cédula *
            </label>
            <input
              type="text"
              inputMode="numeric"
              minLength={5}
              maxLength={20}
              title="Número de cédula: solo números, mínimo 5 dígitos"
              required
              value={formData.cedula}
              onChange={(e) => setFormData({ ...formData, cedula: soloDigitos(e.target.value) })}
              placeholder="Ej. 1001234567"
              className="w-full px-3.5 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm disabled:bg-slate-100"
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
              Nombre Completo *
            </label>
            <input
              type="text"
              required
              value={formData.nombre}
              onChange={(e) => setFormData({ ...formData, nombre: e.target.value })}
              placeholder="Ej. Carlos Alberto Restrepo"
              className="w-full px-3.5 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                Teléfono / Celular *
              </label>
              <input
                type="tel"
                inputMode="numeric"
                required
                minLength={7}
                maxLength={20}
                title="Teléfono / Celular: solo números, mínimo 7 dígitos"
                value={formData.telefono}
                onChange={(e) => setFormData({ ...formData, telefono: soloDigitos(e.target.value) })}
                placeholder="Ej. 3001234567"
                className="w-full px-3.5 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                Aporte Mensual ($) *
              </label>
              <MoneyInput
                title="Aporte mensual: solo números (máximo 2 decimales)"
                required
                value={formData.aporte_mensual}
                onChange={(e) => setFormData({ ...formData, aporte_mensual: soloMonto(e.target.value) })}
                className="w-full px-3.5 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
              Dirección de Residencia *
            </label>
            <input
              type="text"
              required
              minLength={3}
              maxLength={200}
              title="Dirección de residencia: mínimo 3 caracteres"
              value={formData.residencia}
              onChange={(e) => setFormData({ ...formData, residencia: e.target.value })}
              placeholder="Ej. Carrera 45 # 12-30"
              className="w-full px-3.5 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
            />
          </div>

          <div className="flex justify-end gap-2 pt-3">
            <button
              type="button"
              onClick={() => setIsSocioModalOpen(false)}
              className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={submittingSocio}
              className="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-xl disabled:opacity-50"
            >
              {submittingSocio ? "Guardando..." : editingSocio ? "Actualizar Socio" : "Guardar Socio"}
            </button>
          </div>
        </form>
      </Modal>

      {/* Modal Perfil / Estado de Cuenta Individual */}
      <Modal
        isOpen={isProfileModalOpen}
        onClose={() => setIsProfileModalOpen(false)}
        title={selectedSocioProfile ? `Estado de Cuenta — ${selectedSocioProfile.nombre}` : "Estado de Cuenta"}
        maxWidth="max-w-2xl"
      >
        {loadingProfile || !selectedSocioProfile ? (
          <div className="py-12 text-center text-slate-400">
            <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
            Cargando estado financiero del socio...
          </div>
        ) : (
          <div className="space-y-6">
            {/* Resumen de Cifras */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="p-4 bg-emerald-50 border border-emerald-100 rounded-xl">
                <p className="text-xs font-bold text-emerald-800 uppercase">Aportes mensuales</p>
                <p className="text-xl font-black text-emerald-700 mt-1">
                  {formatMoney(selectedSocioProfile.total_ahorrado)}
                </p>
              </div>
              <div className="p-4 bg-sky-50 border border-sky-100 rounded-xl">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs font-bold text-sky-800 uppercase">Total ahorrado</p>
                  <button
                    type="button"
                    onClick={() => imprimirTotalAhorrado(selectedSocioProfile)}
                    className="px-2.5 py-1 bg-sky-500 hover:bg-sky-600 text-white text-[11px] font-bold rounded-lg shadow-md shadow-sky-500/20 transition-all whitespace-nowrap"
                  >
                    Imprimir / Exportar
                  </button>
                </div>
                <p className="text-xl font-black text-sky-700 mt-1">
                  {formatMoney(selectedSocioProfile.total_ahorrado_socio?.total)}
                </p>
                <p className="text-[10px] text-sky-600 mt-0.5">Aportes, intereses, actividades y bien común</p>
              </div>
              <div className="p-4 bg-purple-50 border border-purple-100 rounded-xl">
                <p className="text-xs font-bold text-purple-800 uppercase">Deuda Créditos</p>
                <p className="text-xl font-black text-purple-700 mt-1">
                  {formatMoney(selectedSocioProfile.saldo_prestamos_pendiente)}
                </p>
              </div>
              <div className="p-4 bg-rose-50 border border-rose-100 rounded-xl">
                <p className="text-xs font-bold text-rose-800 uppercase">Multas Impagas</p>
                <p className="text-xl font-black text-rose-700 mt-1">
                  {formatMoney(selectedSocioProfile.total_multas_pendientes)}
                </p>
              </div>
            </div>

            {/* Acciones Rápidas */}
            <div className="flex justify-end">
              <button
                onClick={() => setIsMovementModalOpen(true)}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 shadow-xs"
              >
                <PlusCircle className="w-4 h-4" />
                Cargar multa
              </button>
            </div>

            {/* Aportes mensuales y multas (una línea por registro) */}
            <div className="space-y-3">
              <AportesMensuales socio={selectedSocioProfile} onRegistrado={reloadProfile} />
              <MultasSocio socio={selectedSocioProfile} onRegistrado={reloadProfile} />
              <DeudasCredito socio={selectedSocioProfile} />
              <ActividadesSocio socio={selectedSocioProfile} onRegistrado={reloadProfile} />
              <DeduccionesSocio socio={selectedSocioProfile} />
            </div>

            {/* Historial de Transacciones */}
            <div>
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                  Historial de Movimientos
                </h4>
                <div className="flex flex-wrap gap-2">
                  <select
                    value={historialOrden}
                    onChange={(e) => setHistorialOrden(e.target.value)}
                    aria-label="Ordenar historial"
                    className="px-2 py-1 rounded-lg border border-slate-200 bg-white text-[11px] font-semibold text-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  >
                    <option value="fecha_desc">Fecha: más reciente</option>
                    <option value="fecha_asc">Fecha: más antigua</option>
                    <option value="accion">Por acción</option>
                  </select>
                  <select
                    value={historialTipo}
                    onChange={(e) => setHistorialTipo(e.target.value)}
                    aria-label="Filtrar historial por acción"
                    className="px-2 py-1 rounded-lg border border-slate-200 bg-white text-[11px] font-semibold text-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  >
                    <option value="TODOS">Todas las acciones</option>
                    {Object.entries(ACCIONES_MOVIMIENTO).map(([valor, etiqueta]) => (
                      <option key={valor} value={valor}>{etiqueta}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="max-h-56 overflow-y-auto divide-y divide-slate-100 border border-slate-100 rounded-xl">
                {historialVisible.length > 0 ? (
                  historialVisible.map((t) => (
                    <div key={t.id} className="p-3 flex items-center justify-between text-xs hover:bg-slate-50/50">
                      <div>
                        <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-bold mr-2 ${
                          t.tipo_movimiento === "APORTE"
                            ? "bg-emerald-100 text-emerald-800"
                            : t.tipo_movimiento === "MULTA"
                            ? "bg-rose-100 text-rose-800"
                            : TIPO_MOV_PRESTAMO_VALORES.includes(t.tipo_movimiento)
                            ? "bg-purple-100 text-purple-800"
                            : "bg-blue-100 text-blue-800"
                        }`}>
                          {ACCIONES_MOVIMIENTO[t.tipo_movimiento] || t.tipo_movimiento}
                        </span>
                        {t.anulado && (
                          <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold mr-2 bg-slate-100 text-slate-500">
                            Revertido
                          </span>
                        )}
                        <RichTextDisplay value={t.descripcion || "-"} className={`font-medium ${t.anulado ? "text-slate-400 line-through" : "text-slate-700"}`} />
                        <p className="text-[10px] text-slate-400 mt-0.5">{formatDate(t.fecha)}</p>
                      </div>
                      <p className={`font-bold ${t.anulado ? "text-slate-400 line-through" : "text-slate-800"}`}>{formatMoney(t.monto)}</p>
                    </div>
                  ))
                ) : (
                  <div className="p-4 text-center text-xs text-slate-400">
                    {historialTipo === "TODOS" ? "Sin movimientos registrados." : "No hay movimientos de esta acción."}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* Modal Registrar Movimiento Financiero */}
      <Modal
        isOpen={isMovementModalOpen}
        onClose={() => setIsMovementModalOpen(false)}
        title="Cargar multa al socio"
      >
        <form onSubmit={handleCreateMovement} className="space-y-4">
          <div>
            <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
              Monto en Dinero ($) *
            </label>
            <MoneyInput
              required
              value={movementData.monto}
              onChange={(e) => setMovementData({ ...movementData, monto: e.target.value })}
              placeholder="Ej. 150000"
              className="w-full px-3.5 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
              Fecha *
            </label>
            <input
              type="date"
              required
              max={fechaLocalISO()}
              value={movementData.fecha}
              onChange={(e) => setMovementData({ ...movementData, fecha: e.target.value })}
              className="w-full px-3.5 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
            />
            <p className="text-[11px] text-slate-400 mt-1">Día en que se cargó la multa.</p>
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
              Descripción / Concepto
            </label>
            <RichTextField
              value={movementData.descripcion}
              onChange={(value) => setMovementData({ ...movementData, descripcion: value })}
              placeholder="Ej. Inasistencia a reunión"
              rows={2}
            />
          </div>

          <div className="flex justify-end gap-2 pt-3">
            <button
              type="button"
              onClick={() => setIsMovementModalOpen(false)}
              className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={submittingMovement}
              className="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-xl disabled:opacity-50"
            >
              {submittingMovement ? "Cargando..." : "Cargar multa"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
