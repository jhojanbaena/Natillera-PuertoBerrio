import React, { useEffect, useState } from "react";
import { SquareTerminal, AlertTriangle, Eye, Users, Hash, Ban, Save, CheckCircle2 } from "lucide-react";
import api from "../api/client";

const MODOS = [
  {
    valor: "TODOS",
    titulo: "Todos los socios",
    detalle: "Incluye a los socios que se registren después.",
    icono: Users,
  },
  {
    valor: "RANGO",
    titulo: "Rango de ID",
    detalle: "Solo los socios con ID real entre el inicial y el final. Un socio nuevo fuera del rango no entra.",
    icono: Hash,
  },
  {
    valor: "DESACTIVADO",
    titulo: "Acceso desactivado",
    detalle: "Nadie entra y se cierran las sesiones de socios que estén abiertas.",
    icono: Ban,
  },
];

const describir = (c) => {
  if (!c) return "";
  if (c.modo === "TODOS") return "Todos los socios";
  if (c.modo === "RANGO") return `Socios con ID del ${c.id_inicio} al ${c.id_fin}`;
  return "Acceso desactivado";
};

const soloDigitos = (valor) => valor.replace(/\D/g, "").slice(0, 9);

// Permitir vista a los socios: los socios autorizados entran con su cédula y solo ven su ficha.
const VistaSocios = () => {
  const [config, setConfig] = useState(null);
  const [modo, setModo] = useState("DESACTIVADO");
  const [inicio, setInicio] = useState("");
  const [fin, setFin] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [mensaje, setMensaje] = useState(null);

  const aplicar = (datos) => {
    setConfig(datos);
    setModo(datos.modo);
    setInicio(datos.id_inicio ? String(datos.id_inicio) : "");
    setFin(datos.id_fin ? String(datos.id_fin) : "");
  };

  useEffect(() => {
    api.get("/panel/vista-socios")
      .then((r) => aplicar(r.data))
      .catch(() => setMensaje({ tipo: "error", texto: "No se pudo cargar la configuración." }));
  }, []);

  const guardar = async (e) => {
    e.preventDefault();
    setMensaje(null);
    if (modo === "RANGO") {
      if (!inicio || !fin) {
        setMensaje({ tipo: "error", texto: "Indica el ID inicial y el ID final." });
        return;
      }
      if (Number(fin) < Number(inicio)) {
        setMensaje({ tipo: "error", texto: "El ID final debe ser mayor o igual al ID inicial." });
        return;
      }
    }
    try {
      setGuardando(true);
      const body = modo === "RANGO"
        ? { modo, id_inicio: Number(inicio), id_fin: Number(fin) }
        : { modo };
      const { data } = await api.put("/panel/vista-socios", body);
      aplicar(data);
      setMensaje({ tipo: "ok", texto: "Configuración guardada." });
    } catch (err) {
      const detalle = err.response?.data?.detail;
      setMensaje({
        tipo: "error",
        texto: typeof detalle === "string" ? detalle : "No se pudo guardar. Revisa los datos.",
      });
    } finally {
      setGuardando(false);
    }
  };

  const activo = config?.modo;
  const cambios = config && (modo !== config.modo || (modo === "RANGO" && (
    String(config.id_inicio ?? "") !== inicio || String(config.id_fin ?? "") !== fin
  )));

  return (
    <section className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <div className="p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-black text-slate-800 flex items-center gap-2">
            <Eye className="w-5 h-5 text-purple-600" />
            Permitir vista a los socios
          </h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Los socios autorizados entran con la pestaña «Soy socio» usando su cédula como usuario y contraseña, y solo ven su ficha de Total ahorrado.
          </p>
        </div>
        {config && (
          <span
            className={`shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold border ${
              activo === "DESACTIVADO"
                ? "bg-slate-100 text-slate-600 border-slate-200"
                : "bg-emerald-50 text-emerald-700 border-emerald-200"
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${activo === "DESACTIVADO" ? "bg-slate-400" : "bg-emerald-500"}`} />
            Activa: {describir(config)}
          </span>
        )}
      </div>

      <form onSubmit={guardar} className="p-5 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3" role="radiogroup" aria-label="Modalidad de acceso">
          {MODOS.map(({ valor, titulo, detalle, icono: Icono }) => {
            const elegido = modo === valor;
            return (
              <label
                key={valor}
                className={`relative cursor-pointer p-4 rounded-xl border-2 transition-all ${
                  elegido ? "border-purple-500 bg-purple-50/60" : "border-slate-200 hover:border-slate-300"
                }`}
              >
                <input
                  type="radio"
                  name="modo"
                  value={valor}
                  checked={elegido}
                  onChange={() => setModo(valor)}
                  className="sr-only"
                />
                <div className="flex items-center gap-2">
                  <Icono className={`w-5 h-5 ${elegido ? "text-purple-600" : "text-slate-400"}`} />
                  <span className="font-bold text-slate-800 text-sm">{titulo}</span>
                  {activo === valor && (
                    <span className="ml-auto text-[10px] font-bold uppercase tracking-wider text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full">
                      Activa
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-1.5">{detalle}</p>
              </label>
            );
          })}
        </div>

        {modo === "RANGO" && (
          <div className="grid grid-cols-2 gap-3 max-w-sm">
            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ID inicial</label>
              <input
                type="text"
                inputMode="numeric"
                value={inicio}
                onChange={(e) => setInicio(soloDigitos(e.target.value))}
                className="w-full px-3 py-2.5 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500 text-sm"
                placeholder="Ej. 1"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ID final</label>
              <input
                type="text"
                inputMode="numeric"
                value={fin}
                onChange={(e) => setFin(soloDigitos(e.target.value))}
                className="w-full px-3 py-2.5 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500 text-sm"
                placeholder="Ej. 136"
              />
            </div>
          </div>
        )}

        {mensaje && (
          <p className={`text-sm font-medium flex items-center gap-2 ${mensaje.tipo === "ok" ? "text-emerald-700" : "text-rose-700"}`}>
            {mensaje.tipo === "ok" ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
            {mensaje.texto}
          </p>
        )}

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2 border-t border-slate-100">
          {config ? (
            <p className="text-xs text-slate-500">
              Con la configuración activa pueden entrar <strong className="text-slate-700">{config.socios_con_acceso}</strong> socios
              {config.socios_bloqueados > 0 && (
                <> · {config.socios_bloqueados} bloqueados por cédula provisional</>
              )}
              {config.actualizado_por && (
                <> · Última modificación: {config.actualizado_por}
                  {config.actualizado_en && `, ${new Date(config.actualizado_en).toLocaleString("es-CO")}`}</>
              )}
            </p>
          ) : <span />}
          <button
            type="submit"
            disabled={guardando || !config}
            className="shrink-0 inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-purple-600 hover:bg-purple-700 text-white text-sm font-bold rounded-xl shadow-md shadow-purple-600/20 transition-all disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            {guardando ? "Guardando..." : cambios ? "Guardar cambios" : "Guardar"}
          </button>
        </div>
      </form>
    </section>
  );
};

// Panel del Desarrollador: exclusivo de ese rol.
export const Panel = () => {
  const [estado, setEstado] = useState("cargando");

  useEffect(() => {
    api.get("/panel")
      .then(() => setEstado("listo"))
      .catch(() => setEstado("error"));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl md:text-3xl font-black text-slate-800 tracking-tight flex items-center gap-2.5">
          <SquareTerminal className="w-7 h-7 text-purple-600" />
          Panel
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">Apartado exclusivo del rol Desarrollador.</p>
      </div>

      {estado === "error" && (
        <div className="p-6 bg-rose-50 border border-rose-200 rounded-2xl text-rose-700 text-sm">
          <p className="font-bold flex items-center gap-2"><AlertTriangle className="w-5 h-5" /> No se pudo verificar el acceso al Panel.</p>
        </div>
      )}
      {estado === "listo" && <VistaSocios />}
    </div>
  );
};
