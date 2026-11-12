import React, { useCallback, useEffect, useState } from "react";
import { CalendarRange, Plus, Eye, Users, PiggyBank, BadgePercent, Receipt, AlertTriangle, CheckCircle2, Lock } from "lucide-react";
import api from "../api/client";
import { useAuth } from "../context/AuthContext";
import { usePeriodo } from "../context/PeriodoContext";
import { Modal } from "../components/Modal";
import { formatMoney, formatDate } from "../utils/formatters";

const mensajeError = (err, porDefecto) => {
  const detail = err?.response?.data?.detail;
  return typeof detail === "string" ? detail : porDefecto;
};

// Historial de años de la natillera y creación de un año nuevo.
export const Anios = () => {
  const { user } = useAuth();
  const isAdmin = !!user?.is_admin;
  const { cambiarAnio, volverAlActivo } = usePeriodo();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [confirmando, setConfirmando] = useState(false);
  const [entiendo, setEntiendo] = useState(false);
  const [creando, setCreando] = useState(false);
  const [errorCrear, setErrorCrear] = useState("");

  const cargar = useCallback(async () => {
    try {
      setError("");
      const res = await api.get("/periodos");
      setData(res.data);
    } catch (err) {
      console.error(err);
      setError(mensajeError(err, "No se pudieron cargar los años de la natillera."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const abrirConfirmacion = () => {
    setEntiendo(false);
    setErrorCrear("");
    setConfirmando(true);
  };

  const crearAnio = async () => {
    if (!entiendo || creando) return;
    setCreando(true);
    setErrorCrear("");
    try {
      await api.post("/periodos", { anio: data.proximo_anio });
      // El año nuevo queda activo: se abre la aplicación en ese año.
      volverAlActivo();
    } catch (err) {
      console.error(err);
      setErrorCrear(mensajeError(err, "No se pudo crear el año. No se realizó ningún cambio."));
      setCreando(false);
      cargar();
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="w-10 h-10 border-4 border-purple-500 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  const anioOrigen = data?.anio_activo;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-black text-slate-800 tracking-tight flex items-center gap-2.5">
            <CalendarRange className="w-7 h-7 text-purple-600" />
            Años de la Natillera
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Cada año funciona como un periodo independiente. Los años anteriores se conservan intactos y solo se pueden consultar.
          </p>
        </div>
        {isAdmin && data && (
          <button
            onClick={abrirConfirmacion}
            className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-purple-700 hover:bg-purple-800 text-white text-sm font-bold shadow-md shadow-purple-500/20 transition-colors"
          >
            <Plus className="w-4 h-4" />
            CREAR NUEVO AÑO
          </button>
        )}
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-sm font-medium">{error}</div>
      )}

      {data && (
        <div className="grid gap-4 md:grid-cols-2">
          {data.periodos.map((p) => {
            const enPantalla = p.anio === data.anio_consultado;
            return (
              <div
                key={p.anio}
                className={`bg-white rounded-2xl border p-5 shadow-xs ${
                  enPantalla ? "border-purple-300 ring-2 ring-purple-100" : "border-slate-200/80"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-3xl font-black text-slate-800 tracking-tight">{p.anio}</p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {p.copiado_de_anio
                        ? `Creado ${p.created_at ? formatDate(p.created_at) : ""} · ${p.socios_copiados} socios copiados de ${p.copiado_de_anio}`
                        : "Año inicial de la natillera"}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1.5">
                    {p.activo ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800">
                        <CheckCircle2 className="w-3.5 h-3.5" /> AÑO ACTIVO
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-600">
                        <Lock className="w-3.5 h-3.5" /> SOLO CONSULTA
                      </span>
                    )}
                    {enPantalla && (
                      <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-purple-100 text-purple-800">EN PANTALLA</span>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 mt-4">
                  <Dato icon={Users} label="Socios" valor={`${p.socios} (${p.socios_activos} activos)`} />
                  <Dato icon={PiggyBank} label="Ahorro total" valor={formatMoney(p.total_ahorro)} />
                  <Dato icon={BadgePercent} label="Préstamos" valor={`${p.prestamos} · ${formatMoney(p.total_prestado)}`} />
                  <Dato icon={Receipt} label="Gastos generales" valor={formatMoney(p.total_gastos)} />
                </div>

                {!enPantalla && (
                  <button
                    onClick={() => cambiarAnio(p.anio)}
                    className="mt-4 w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded-xl text-sm font-semibold text-purple-700 bg-purple-50 hover:bg-purple-100 transition-colors"
                  >
                    <Eye className="w-4 h-4" />
                    {p.activo ? "Volver al año activo" : `Consultar ${p.anio}`}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      <Modal isOpen={confirmando} onClose={() => !creando && setConfirmando(false)} title={`Crear el año ${data?.proximo_anio ?? ""}`}>
        <div className="space-y-4 text-sm text-slate-600">
          <div className="flex gap-3 p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800">
            <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
            <p>
              Se va a crear un <strong>nuevo periodo</strong>. Los registros financieros comenzarán desde <strong>cero</strong>:
              ahorros, préstamos, abonos, intereses, bien común, gastos, contabilidad, liquidación, retiros y demás movimientos.
            </p>
          </div>
          <ul className="list-disc pl-5 space-y-1">
            <li>
              Los socios del año <strong>{anioOrigen}</strong> se copiarán al año <strong>{data?.proximo_anio}</strong> con sus datos personales.
            </li>
            <li>El año {anioOrigen} y los anteriores <strong>no se borran</strong>: quedan guardados y se podrán consultar.</li>
            <li>El año {data?.proximo_anio} pasará a ser el año activo.</li>
          </ul>
          <label className="flex items-start gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={entiendo}
              onChange={(e) => setEntiendo(e.target.checked)}
              className="mt-0.5 w-4 h-4 accent-purple-700"
            />
            <span className="font-medium text-slate-700">Entiendo que el año {data?.proximo_anio} inicia sin registros financieros.</span>
          </label>
          {errorCrear && (
            <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 font-medium">{errorCrear}</div>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <button
              onClick={() => setConfirmando(false)}
              disabled={creando}
              className="px-4 py-2 rounded-xl text-sm font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 disabled:opacity-50"
            >
              Cancelar
            </button>
            <button
              onClick={crearAnio}
              disabled={!entiendo || creando}
              className="px-4 py-2 rounded-xl text-sm font-bold text-white bg-purple-700 hover:bg-purple-800 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {creando ? "Creando..." : `Crear año ${data?.proximo_anio ?? ""}`}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

const Dato = ({ icon: Icon, label, valor }) => (
  <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
    <p className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
      <Icon className="w-3.5 h-3.5" /> {label}
    </p>
    <p className="text-sm font-bold text-slate-800 mt-1 truncate">{valor}</p>
  </div>
);
