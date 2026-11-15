import React, { useEffect, useMemo, useState } from "react";
import { Check, Plus, Trash2, Undo2 } from "lucide-react";
import { MoneyInput } from "./MoneyInput";
import { formatMoney } from "../utils/formatters";

// Lista de líneas "nombre + valor" que se agregan, editan y eliminan una a una.
// Cada línea se guarda en el backend con su botón ✓ (o Enter); las nuevas que aún no
// se guardan pueden descartarse. Los valores usan MoneyInput (puntos de miles).

const num = (v) => Number(v || 0);
let secuencia = 0;
const nuevaClave = () => `nueva-${++secuencia}`;

const desdeItem = (item, campoNombre, campoValor) => ({
  clave: `id-${item.id}`,
  id: item.id,
  nombre: item[campoNombre] ?? "",
  valor: String(item[campoValor] ?? ""),
  original: { nombre: item[campoNombre] ?? "", valor: num(item[campoValor]) },
});

export const LineasEditables = ({
  items,
  campoNombre = "nombre",
  campoValor = "valor",
  textoBoton,
  placeholderNombre,
  etiquetaNombre = "Descripción",
  etiquetaValor = "Valor",
  vacio,
  editable = true,
  onCrear,
  onGuardar,
  onEliminar,
  onPendientesChange,
  onLineasChange,
  color = "purple",
}) => {
  const [lineas, setLineas] = useState(() => items.map((i) => desdeItem(i, campoNombre, campoValor)));
  const [ocupado, setOcupado] = useState(null);
  const [error, setError] = useState("");

  // Al recargar desde el servidor se conservan las líneas nuevas y las ediciones sin guardar.
  useEffect(() => {
    setLineas((actuales) => {
      const editadas = new Map(actuales.filter((l) => l.id != null).map((l) => [l.id, l]));
      const guardadas = items.map((item) => {
        const base = desdeItem(item, campoNombre, campoValor);
        const previa = editadas.get(item.id);
        if (previa && (previa.nombre !== previa.original.nombre || num(previa.valor) !== previa.original.valor)) {
          return { ...base, nombre: previa.nombre, valor: previa.valor };
        }
        return base;
      });
      return [...guardadas, ...actuales.filter((l) => l.id == null)];
    });
  }, [items, campoNombre, campoValor]);

  const sucia = (l) => l.id == null || l.nombre !== l.original.nombre || num(l.valor) !== l.original.valor;
  const pendientes = useMemo(() => lineas.filter(sucia).length, [lineas]);
  useEffect(() => { onPendientesChange?.(pendientes); }, [pendientes, onPendientesChange]);
  // Informa las líneas tal como se ven en pantalla (incluye las que aún no se guardan),
  // para que los totales de otros recuadros se actualicen al instante.
  useEffect(() => { onLineasChange?.(lineas); }, [lineas, onLineasChange]);

  const cambiar = (clave, campo, valor) =>
    setLineas((ls) => ls.map((l) => (l.clave === clave ? { ...l, [campo]: valor } : l)));

  const agregar = () => {
    setError("");
    setLineas((ls) => [...ls, { clave: nuevaClave(), id: null, nombre: "", valor: "", original: null }]);
  };

  const ejecutar = async (l, accion) => {
    setOcupado(l.clave);
    setError("");
    try {
      await accion();
      return true;
    } catch (err) {
      const detalle = err?.response?.data?.detail;
      setError(Array.isArray(detalle) ? detalle.map((d) => d.msg).join("; ") : detalle || "No se pudo guardar el cambio.");
      return false;
    } finally {
      setOcupado(null);
    }
  };

  const guardar = async (l) => {
    if (!l.nombre.trim()) return setError(`Escribe el ${etiquetaNombre.toLowerCase()}.`);
    if (l.valor === "" || !Number.isFinite(num(l.valor)) || num(l.valor) < 0) return setError("Escribe un valor válido.");
    const valor = num(l.valor).toFixed(2);
    if (l.id == null) {
      const ok = await ejecutar(l, () => onCrear(l.nombre.trim(), valor));
      // La línea guardada vuelve desde el servidor; se quita el borrador.
      if (ok) setLineas((ls) => ls.filter((x) => x.clave !== l.clave));
    } else {
      await ejecutar(l, () => onGuardar(l.id, l.nombre.trim(), valor));
    }
  };

  const eliminar = async (l) => {
    if (l.id == null) {
      setLineas((ls) => ls.filter((x) => x.clave !== l.clave));
      return;
    }
    if (!window.confirm(`¿Eliminar "${l.original.nombre}" (${formatMoney(l.original.valor)})?`)) return;
    const ok = await ejecutar(l, () => onEliminar(l.id));
    if (ok) setLineas((ls) => ls.filter((x) => x.clave !== l.clave));
  };

  const deshacer = (l) =>
    setLineas((ls) => ls.map((x) => (x.clave === l.clave ? { ...x, nombre: l.original.nombre, valor: String(l.original.valor) } : x)));

  const anillo = color === "emerald" ? "focus:ring-emerald-500" : "focus:ring-purple-500";
  const input = `w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 ${anillo} text-sm disabled:bg-slate-50 disabled:text-slate-500`;

  return (
    <div className="space-y-3">
      {lineas.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-400">{vacio}</p>
      ) : (
        <div className="space-y-2">
          <div className="hidden sm:grid grid-cols-[minmax(0,1fr)_180px_88px] gap-2 px-1 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
            <span>{etiquetaNombre}</span>
            <span className="text-right">{etiquetaValor}</span>
            <span />
          </div>
          {lineas.map((l) => {
            const pendiente = sucia(l);
            const enCurso = ocupado === l.clave;
            const enter = (e) => { if (e.key === "Enter") { e.preventDefault(); guardar(l); } };
            return (
              <div
                key={l.clave}
                className={`grid grid-cols-[minmax(0,1fr)_88px] sm:grid-cols-[minmax(0,1fr)_180px_88px] gap-2 items-center p-2 rounded-xl border ${
                  pendiente ? "border-amber-200 bg-amber-50/40" : "border-slate-100 bg-white"
                } ${enCurso ? "opacity-60 pointer-events-none" : ""}`}
              >
                <input
                  type="text"
                  maxLength={campoNombre === "descripcion" ? 150 : 120}
                  value={l.nombre}
                  disabled={!editable}
                  onChange={(e) => cambiar(l.clave, "nombre", e.target.value)}
                  onKeyDown={enter}
                  placeholder={placeholderNombre}
                  aria-label={etiquetaNombre}
                  className={`${input} col-span-2 sm:col-span-1`}
                />
                <MoneyInput
                  value={l.valor}
                  disabled={!editable}
                  onChange={(e) => cambiar(l.clave, "valor", e.target.value)}
                  onKeyDown={enter}
                  placeholder="0"
                  aria-label={etiquetaValor}
                  className={`${input} text-right font-bold`}
                />
                <div className="flex items-center justify-end gap-1">
                  {editable && pendiente && (
                    <button
                      type="button"
                      onClick={() => guardar(l)}
                      title="Guardar línea"
                      aria-label="Guardar línea"
                      className="p-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white"
                    >
                      <Check className="w-4 h-4" />
                    </button>
                  )}
                  {editable && pendiente && l.id != null && (
                    <button
                      type="button"
                      onClick={() => deshacer(l)}
                      title="Deshacer cambios"
                      aria-label="Deshacer cambios"
                      className="p-2 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                    >
                      <Undo2 className="w-4 h-4" />
                    </button>
                  )}
                  {editable && (
                    <button
                      type="button"
                      onClick={() => eliminar(l)}
                      title="Eliminar línea"
                      aria-label="Eliminar línea"
                      className="p-2 rounded-lg text-rose-500 hover:text-rose-700 hover:bg-rose-50"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {error && <p className="p-3 rounded-xl bg-rose-50 border border-rose-100 text-xs text-rose-700">{error}</p>}
      {pendientes > 0 && (
        <p className="text-[11px] text-amber-700">
          {pendientes} línea{pendientes === 1 ? "" : "s"} sin guardar: presiona ✓ o Enter para guardar.
        </p>
      )}

      {editable && (
        <button
          type="button"
          onClick={agregar}
          className={`w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 border-2 border-dashed rounded-xl text-sm font-black transition-colors ${
            color === "emerald"
              ? "border-emerald-200 text-emerald-700 hover:bg-emerald-50"
              : "border-purple-200 text-purple-700 hover:bg-purple-50"
          }`}
        >
          <Plus className="w-4 h-4" /> {textoBoton}
        </button>
      )}
    </div>
  );
};
