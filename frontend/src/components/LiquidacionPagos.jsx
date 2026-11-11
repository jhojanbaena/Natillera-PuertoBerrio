// Piezas de UI para el control de pagos de la Liquidación anual.
import React, { useState } from "react";
import {
  Banknote, Smartphone, CheckCircle2, Circle, Undo2, Wallet, Pencil, NotebookPen, Search, AlertTriangle,
} from "lucide-react";
import { Modal } from "./Modal";
import { formatMoney } from "../utils/formatters";

export const METODOS = {
  EFECTIVO: { label: "Efectivo", Icon: Banknote },
  TRANSFERENCIA: { label: "Transferencia", Icon: Smartphone },
};

const num = (v) => parseFloat(v ?? 0) || 0;

export const formatFechaPago = (iso) =>
  iso
    ? new Date(iso).toLocaleString("es-CO", {
        year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
      })
    : "—";

/* ---------- Resumen del dinero general ---------- */
export const FondoResumen = ({ control, isAdmin, onAjustar }) => {
  if (!control) return null;
  const general = num(control.monto_general);
  const usado = num(control.monto_utilizado);
  const porcentaje = general > 0 ? Math.min(100, (usado / general) * 100) : 0;

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-5 print:hidden">
      <div className="flex items-center justify-between gap-3 mb-4">
        <h3 className="font-bold text-slate-800 flex items-center gap-2">
          <Wallet className="w-5 h-5 text-sky-500" /> Dinero para liquidaciones {control.anio}
        </h3>
        <span className="text-xs font-bold text-slate-500">
          {control.total_liquidados} de {control.total_socios} socios liquidados
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="rounded-xl bg-slate-50 border border-slate-100 p-3">
          <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500 flex items-center justify-between">
            Dinero general
            {isAdmin && (
              <button onClick={onAjustar} title="Ajustar dinero general" className="p-1 -m-1 rounded-md text-slate-400 hover:text-sky-600 hover:bg-white">
                <Pencil className="w-3.5 h-3.5" />
              </button>
            )}
          </p>
          <p className="text-xl font-black text-slate-800 mt-0.5">{formatMoney(control.monto_general)}</p>
          <p className="text-[11px] text-slate-400">
            {control.fondo_definido ? "Valor guardado para este año" : "Sugerido: suma de los netos a recibir"}
          </p>
        </div>
        <div className="rounded-xl bg-amber-50 border border-amber-100 p-3">
          <p className="text-[11px] font-bold uppercase tracking-wider text-amber-700">Dinero utilizado</p>
          <p className="text-xl font-black text-amber-700 mt-0.5">{formatMoney(control.monto_utilizado)}</p>
          <p className="text-[11px] text-amber-600">Entregado a socios liquidados</p>
        </div>
        <div className="rounded-xl bg-emerald-50 border border-emerald-100 p-3">
          <p className="text-[11px] font-bold uppercase tracking-wider text-emerald-700">Saldo disponible</p>
          <p className={`text-xl font-black mt-0.5 ${num(control.saldo_disponible) < 0 ? "text-rose-700" : "text-emerald-700"}`}>
            {formatMoney(control.saldo_disponible)}
          </p>
          <p className="text-[11px] text-emerald-600">Para seguir liquidando</p>
        </div>
      </div>
      <div className="mt-4 h-2 rounded-full bg-slate-100 overflow-hidden" aria-hidden="true">
        <div className="h-full bg-amber-400 transition-all" style={{ width: `${porcentaje}%` }} />
      </div>
    </div>
  );
};

/* ---------- Botones pequeños junto al neto a recibir ---------- */
export const BotonesPago = ({ item, isAdmin, onPagar }) => {
  if (!item) return null;
  const pago = item.pago;
  if (pago) {
    const { Icon, label } = METODOS[pago.metodo_pago] || METODOS.EFECTIVO;
    return (
      <span
        title={`Liquidado en ${label.toLowerCase()} el ${formatFechaPago(pago.fecha_pago)}`}
        className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-emerald-100 text-emerald-700 text-[11px] font-bold whitespace-nowrap"
      >
        <CheckCircle2 className="w-3.5 h-3.5" />
        <Icon className="w-3.5 h-3.5" />
        Liquidado
      </span>
    );
  }
  const sinValor = num(item.total_neto_entregar) < 0;
  const disabled = !isAdmin || sinValor;
  const motivo = !isAdmin ? "Solo un administrador puede registrar pagos" : sinValor ? "El socio debe dinero; no hay valor a entregar" : null;
  return (
    <span className="inline-flex gap-1">
      {Object.entries(METODOS).map(([metodo, { label, Icon }]) => (
        <button
          key={metodo}
          type="button"
          disabled={disabled}
          onClick={() => onPagar(item, metodo)}
          title={motivo || `Pagar en ${label.toLowerCase()}`}
          aria-label={`Pagar liquidación de ${item.nombre} en ${label.toLowerCase()}`}
          className="p-1.5 rounded-lg border border-slate-200 bg-white text-slate-500 hover:text-sky-600 hover:border-sky-300 hover:bg-sky-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-white disabled:hover:text-slate-500 disabled:hover:border-slate-200"
        >
          <Icon className="w-3.5 h-3.5" />
        </button>
      ))}
    </span>
  );
};

/* ---------- Apartado tipo "Notas" ---------- */
export const ControlLiquidados = ({ control, isAdmin, onPagar, onGestionar }) => {
  const [filtro, setFiltro] = useState("todos");
  const [busqueda, setBusqueda] = useState("");
  if (!control) return null;

  const texto = busqueda.trim().toLocaleLowerCase();
  const items = control.socios
    .filter((s) => (filtro === "pendientes" ? !s.liquidado : filtro === "liquidados" ? s.liquidado : true))
    .filter((s) => !texto || `${s.nombre} ${s.cedula ?? ""}`.toLocaleLowerCase().includes(texto))
    .slice()
    .sort((a, b) => Number(a.liquidado) - Number(b.liquidado) || a.nombre.localeCompare(b.nombre, "es"));

  const chips = [
    ["todos", `Todos (${control.total_socios})`],
    ["pendientes", `Pendientes (${control.total_pendientes})`],
    ["liquidados", `Liquidados (${control.total_liquidados})`],
  ];

  return (
    <div className="bg-[#fffdf5] rounded-2xl border border-amber-100 shadow-sm overflow-hidden">
      <div className="px-5 pt-5 pb-3">
        <h3 className="text-xl font-black text-slate-800 flex items-center gap-2">
          <NotebookPen className="w-5 h-5 text-amber-500" /> Control de socios liquidados
        </h3>
        <p className="text-xs text-slate-400 mt-0.5">
          Toca un socio pendiente para registrar su pago. Toca uno liquidado para cambiar el método o revertirlo.
        </p>
        <div className="mt-3 flex flex-col sm:flex-row gap-2">
          <label className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="search"
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Buscar socio"
              className="w-full pl-9 pr-3 py-2 bg-white/80 border border-amber-100 rounded-xl text-sm outline-none focus:border-amber-300 focus:ring-2 focus:ring-amber-100"
            />
          </label>
          <div className="flex gap-1 bg-amber-50 rounded-xl p-1 overflow-x-auto">
            {chips.map(([valor, label]) => (
              <button
                key={valor}
                onClick={() => setFiltro(valor)}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold whitespace-nowrap transition-colors ${
                  filtro === valor ? "bg-white text-amber-700 shadow-sm" : "text-amber-700/70 hover:text-amber-800"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <ul className="border-t border-amber-100/80">
        {items.length === 0 && (
          <li className="px-5 py-10 text-center text-sm text-slate-400">No hay socios en esta vista.</li>
        )}
        {items.map((s) => {
          const pago = s.pago;
          const metodo = pago ? metodoInfo(pago.metodo_pago) : null;
          const sinValor = !pago && num(s.total_neto_entregar) < 0;
          const clickable = isAdmin && !sinValor;
          return (
            <li key={s.socio_id} className="border-b border-amber-100/80 last:border-b-0">
              <button
                type="button"
                disabled={!clickable}
                onClick={() => (pago ? onGestionar(s) : onPagar(s, null))}
                className={`w-full text-left px-5 py-3 flex items-center gap-3 transition-colors ${
                  clickable ? "hover:bg-amber-50/70" : "cursor-default"
                }`}
              >
                {pago ? (
                  <CheckCircle2 className="w-6 h-6 text-emerald-500 shrink-0" />
                ) : (
                  <Circle className="w-6 h-6 text-amber-300 shrink-0" />
                )}
                <span className="flex-1 min-w-0">
                  <span className={`block font-semibold truncate ${pago ? "text-slate-400 line-through decoration-slate-300" : "text-slate-800"}`}>
                    {s.nombre}
                  </span>
                  <span className="block text-xs text-slate-400 truncate">
                    {pago ? (
                      <>
                        {formatMoney(pago.monto)} · {metodo.label} · {formatFechaPago(pago.fecha_pago)}
                      </>
                    ) : sinValor ? (
                      <>Debe {formatMoney(Math.abs(num(s.total_neto_entregar)))} · sin valor a entregar</>
                    ) : (
                      <>Neto a recibir {formatMoney(s.total_neto_entregar)}</>
                    )}
                  </span>
                </span>
                {pago ? (
                  <span className="shrink-0 inline-flex items-center gap-1 px-2 py-1 rounded-full bg-emerald-100 text-emerald-700 text-[11px] font-bold">
                    <metodo.Icon className="w-3.5 h-3.5" /> Liquidado
                  </span>
                ) : (
                  <span className="shrink-0 px-2 py-1 rounded-full bg-amber-100 text-amber-700 text-[11px] font-bold">
                    Pendiente
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

function metodoInfo(metodo) {
  return METODOS[metodo] || METODOS.EFECTIVO;
}

/* ---------- Confirmar un pago ---------- */
export const PagoDialog = ({ dialog, control, busy, error, onClose, onConfirm, onMetodo }) => {
  const item = dialog?.item;
  const neto = num(item?.total_neto_entregar);
  const saldo = num(control?.saldo_disponible);
  const insuficiente = neto > saldo;
  return (
    <Modal isOpen={!!dialog} onClose={busy ? () => {} : onClose} title="Registrar liquidación">
      {item && (
        <div className="space-y-4">
          <div>
            <p className="text-sm text-slate-500">Socio</p>
            <p className="text-lg font-black text-slate-800">{item.nombre}</p>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(METODOS).map(([metodo, { label, Icon }]) => (
              <button
                key={metodo}
                type="button"
                onClick={() => onMetodo(metodo)}
                className={`flex items-center justify-center gap-2 py-3 rounded-xl border text-sm font-bold transition-colors ${
                  dialog.metodo === metodo
                    ? "border-sky-400 bg-sky-50 text-sky-700 ring-2 ring-sky-100"
                    : "border-slate-200 text-slate-600 hover:bg-slate-50"
                }`}
              >
                <Icon className="w-4 h-4" /> {label}
              </button>
            ))}
          </div>
          <dl className="rounded-xl bg-slate-50 border border-slate-100 p-3 text-sm space-y-1.5">
            <div className="flex justify-between"><dt className="text-slate-500">Saldo disponible</dt><dd className="font-bold">{formatMoney(saldo)}</dd></div>
            <div className="flex justify-between"><dt className="text-slate-500">Neto a entregar</dt><dd className="font-bold text-rose-600">- {formatMoney(neto)}</dd></div>
            <div className="flex justify-between border-t border-slate-200 pt-1.5"><dt className="font-bold text-slate-700">Saldo restante</dt><dd className={`font-black ${insuficiente ? "text-rose-700" : "text-emerald-700"}`}>{formatMoney(saldo - neto)}</dd></div>
          </dl>
          {insuficiente && (
            <p className="text-xs text-rose-700 bg-rose-50 border border-rose-100 rounded-xl p-3 flex gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" /> El saldo disponible no alcanza para esta liquidación.
            </p>
          )}
          {error && <p className="text-xs text-rose-700 bg-rose-50 border border-rose-100 rounded-xl p-3">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <button onClick={onClose} disabled={busy} className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-bold">Cancelar</button>
            <button
              onClick={onConfirm}
              disabled={busy || !dialog.metodo || insuficiente}
              className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {busy ? "Guardando..." : "Confirmar pago"}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
};

/* ---------- Gestionar un pago ya registrado ---------- */
export const GestionDialog = ({ item, busy, error, onClose, onCambiarMetodo, onRevertir }) => {
  const [confirmarReversion, setConfirmarReversion] = useState(false);
  const pago = item?.pago;
  const cerrar = () => { if (!busy) { setConfirmarReversion(false); onClose(); } };
  return (
    <Modal isOpen={!!pago} onClose={cerrar} title="Liquidación registrada">
      {pago && (
        <div className="space-y-4">
          <div>
            <p className="text-lg font-black text-slate-800">{item.nombre}</p>
            <p className="text-sm text-slate-500">
              {formatMoney(pago.monto)} entregados el {formatFechaPago(pago.fecha_pago)}
              {pago.usuario_nombre ? ` · registró ${pago.usuario_nombre}` : ""}
            </p>
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">Método de pago</p>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(METODOS).map(([metodo, { label, Icon }]) => (
                <button
                  key={metodo}
                  type="button"
                  disabled={busy || pago.metodo_pago === metodo}
                  onClick={() => onCambiarMetodo(pago, metodo)}
                  className={`flex items-center justify-center gap-2 py-2.5 rounded-xl border text-sm font-bold transition-colors ${
                    pago.metodo_pago === metodo
                      ? "border-emerald-400 bg-emerald-50 text-emerald-700"
                      : "border-slate-200 text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  <Icon className="w-4 h-4" /> {label}
                </button>
              ))}
            </div>
          </div>
          {error && <p className="text-xs text-rose-700 bg-rose-50 border border-rose-100 rounded-xl p-3">{error}</p>}
          {confirmarReversion ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 space-y-2">
              <p className="text-sm text-rose-800">
                ¿Revertir esta liquidación? El socio vuelve a quedar pendiente y {formatMoney(pago.monto)} regresan al saldo disponible.
              </p>
              <div className="flex justify-end gap-2">
                <button onClick={() => setConfirmarReversion(false)} disabled={busy} className="px-3 py-1.5 rounded-lg bg-white text-slate-700 text-xs font-bold border border-slate-200">No</button>
                <button
                  onClick={async () => { const ok = await onRevertir(pago); if (ok) setConfirmarReversion(false); }}
                  disabled={busy}
                  className="px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold disabled:opacity-50"
                >
                  {busy ? "Revirtiendo..." : "Sí, revertir"}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex justify-between gap-2 pt-1">
              <button onClick={() => setConfirmarReversion(true)} disabled={busy} className="px-3 py-2 rounded-xl text-rose-600 hover:bg-rose-50 text-sm font-bold inline-flex items-center gap-1.5">
                <Undo2 className="w-4 h-4" /> Revertir liquidación
              </button>
              <button onClick={cerrar} className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-bold">Cerrar</button>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
};

/* ---------- Ajustar el dinero general ---------- */
export const FondoDialog = ({ open, control, busy, error, onClose, onGuardar }) => {
  // El padre lo monta solo mientras está abierto: el campo arranca con el valor actual.
  const [valor, setValor] = useState(() => String(Math.round(num(control?.monto_general))));
  const monto = num(valor);
  const menorQueUsado = monto < num(control?.monto_utilizado);
  return (
    <Modal isOpen={open} onClose={busy ? () => {} : onClose} title="Dinero general para liquidaciones">
      {control && (
        <form
          className="space-y-4"
          onSubmit={(e) => { e.preventDefault(); if (!menorQueUsado) onGuardar(monto); }}
        >
          <p className="text-sm text-slate-500">
            Valor total con el que cuenta la natillera para liquidar a los socios en {control.anio}.
            La suma de los netos a recibir es {formatMoney(control.socios.reduce((t, s) => t + Math.max(0, num(s.total_neto_entregar)), 0))}.
          </p>
          <input
            type="number"
            min="0"
            step="1"
            required
            value={valor}
            onChange={(e) => setValor(e.target.value)}
            className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-lg font-bold outline-none focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
          />
          {menorQueUsado && (
            <p className="text-xs text-rose-700">No puede ser menor a lo ya entregado ({formatMoney(control.monto_utilizado)}).</p>
          )}
          {error && <p className="text-xs text-rose-700 bg-rose-50 border border-rose-100 rounded-xl p-3">{error}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={onClose} disabled={busy} className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-bold">Cancelar</button>
            <button type="submit" disabled={busy || menorQueUsado} className="px-4 py-2 rounded-xl bg-sky-500 hover:bg-sky-600 text-white text-sm font-bold disabled:opacity-50">
              {busy ? "Guardando..." : "Guardar"}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
};
