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
import { AportesMensuales, DeudasCredito, MultasSocio } from "../components/SocioAportesMultas";
import { formatMoney, formatDate, fechaLocalISO } from "../utils/formatters";

const ACCIONES_MOVIMIENTO = {
  APORTE: "Aporte",
  MULTA: "Multa",
  PAGO_MULTA: "Pago de multa",
  RETIRO_AHORRO: "Retiro de ahorro",
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

  const historialVisible = (selectedSocioProfile?.historial_finanzas || [])
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
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="p-4 bg-emerald-50 border border-emerald-100 rounded-xl">
                <p className="text-xs font-bold text-emerald-800 uppercase">Aportes mensuales</p>
                <p className="text-xl font-black text-emerald-700 mt-1">
                  {formatMoney(selectedSocioProfile.total_ahorrado)}
                </p>
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
                            : "bg-blue-100 text-blue-800"
                        }`}>
                          {ACCIONES_MOVIMIENTO[t.tipo_movimiento] || t.tipo_movimiento}
                        </span>
                        <RichTextDisplay value={t.descripcion || "-"} className="text-slate-700 font-medium" />
                        <p className="text-[10px] text-slate-400 mt-0.5">{formatDate(t.fecha)}</p>
                      </div>
                      <p className="font-bold text-slate-800">{formatMoney(t.monto)}</p>
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
