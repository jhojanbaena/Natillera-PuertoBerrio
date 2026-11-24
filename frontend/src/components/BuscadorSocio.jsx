import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import { Search, X, MapPin } from "lucide-react";

// Buscador dinámico de socios por nombre y apellido.
// - Filtra mientras se escribe (sin tildes ni mayúsculas; cada palabra escrita debe
//   aparecer en el nombre, en cualquier orden: "rest carlos" encuentra "Carlos Restrepo").
// - Cada resultado muestra datos para distinguir socios con nombres parecidos
//   (ID, cédula, residencia y una nota opcional), pero la búsqueda es solo por nombre.
// - Se navega con flechas, Enter elige y Escape cierra.
// - Muestra a lo sumo MAX_RESULTADOS coincidencias: funciona igual con muchos socios.

const MAX_RESULTADOS = 8;

const normalizar = (texto) =>
  String(texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();

const resaltar = (nombre, palabras) => {
  if (!palabras.length) return nombre;
  const base = normalizar(nombre);
  const marcas = new Array(nombre.length).fill(false);
  palabras.forEach((p) => {
    let i = base.indexOf(p);
    while (i !== -1) {
      for (let k = i; k < i + p.length; k += 1) marcas[k] = true;
      i = base.indexOf(p, i + p.length);
    }
  });
  const partes = [];
  let actual = "";
  let marcado = marcas[0];
  [...nombre].forEach((c, i) => {
    if (marcas[i] !== marcado) {
      partes.push({ texto: actual, marcado });
      actual = "";
      marcado = marcas[i];
    }
    actual += c;
  });
  partes.push({ texto: actual, marcado });
  return partes.map((p, i) => (p.marcado ? <mark key={i} className="bg-emerald-100 text-emerald-900 rounded-sm">{p.texto}</mark> : <span key={i}>{p.texto}</span>));
};

export const BuscadorSocio = ({ socios, value, onChange, nota, required, inputClassName = "", placeholder = "Escribe el nombre o apellido del socio..." }) => {
  const [texto, setTexto] = useState("");
  const [abierto, setAbierto] = useState(false);
  const [activo, setActivo] = useState(0);
  const contenedor = useRef(null);
  const lista = useRef(null);
  const idLista = useId();

  const seleccionado = useMemo(() => socios.find((s) => String(s.id) === String(value)) || null, [socios, value]);
  const indice = useMemo(() => socios.map((s) => ({ socio: s, clave: normalizar(s.nombre) })), [socios]);
  const palabras = useMemo(() => normalizar(texto).split(/\s+/).filter(Boolean), [texto]);

  const resultados = useMemo(() => {
    if (!palabras.length) return [];
    return indice
      .filter(({ clave }) => palabras.every((p) => clave.includes(p)))
      .sort((a, b) => {
        // Primero los que empiezan por lo escrito, luego por orden alfabético.
        const ia = a.clave.startsWith(palabras[0]) ? 0 : 1;
        const ib = b.clave.startsWith(palabras[0]) ? 0 : 1;
        return ia - ib || a.socio.nombre.localeCompare(b.socio.nombre, "es");
      })
      .slice(0, MAX_RESULTADOS + 1)
      .map((r) => r.socio);
  }, [indice, palabras]);
  const visibles = resultados.slice(0, MAX_RESULTADOS);
  // Nombres repetidos entre los resultados: se resaltan los datos que los distinguen.
  const repetidos = useMemo(() => {
    const cuenta = {};
    visibles.forEach((s) => { const k = normalizar(s.nombre); cuenta[k] = (cuenta[k] || 0) + 1; });
    return cuenta;
  }, [visibles]);

  useEffect(() => {
    const fuera = (e) => { if (contenedor.current && !contenedor.current.contains(e.target)) setAbierto(false); };
    document.addEventListener("mousedown", fuera);
    return () => document.removeEventListener("mousedown", fuera);
  }, []);

  useEffect(() => {
    lista.current?.querySelector(`[data-indice="${activo}"]`)?.scrollIntoView({ block: "nearest" });
  }, [activo]);

  const elegir = (socio) => {
    onChange(String(socio.id));
    setTexto("");
    setAbierto(false);
  };

  const limpiar = () => {
    onChange("");
    setTexto("");
    setAbierto(true);
  };

  const teclas = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setAbierto(true); setActivo((i) => Math.min(i + 1, visibles.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActivo((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Enter") {
      if (abierto && visibles[activo]) { e.preventDefault(); elegir(visibles[activo]); }
    } else if (e.key === "Escape") { setAbierto(false); }
  };

  if (seleccionado) {
    const extra = nota?.(seleccionado);
    return (
      <div className="flex items-center gap-3 px-3.5 py-2 rounded-xl border border-emerald-300 bg-emerald-50/60 text-sm">
        <div className="flex-1 min-w-0">
          <p className="font-bold text-slate-800 truncate">{seleccionado.nombre}</p>
          <p className="text-[11px] text-slate-500 truncate">
            ID {seleccionado.id} · CC {seleccionado.cedula}
            {seleccionado.residencia ? ` · ${seleccionado.residencia}` : ""}
            {extra ? ` · ${extra}` : ""}
          </p>
        </div>
        <button
          type="button"
          onClick={limpiar}
          className="shrink-0 inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-bold text-slate-500 hover:text-slate-700 hover:bg-white"
          title="Elegir otro socio"
        >
          <X className="w-3.5 h-3.5" /> Cambiar
        </button>
      </div>
    );
  }

  return (
    <div ref={contenedor} className="relative">
      <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
      <input
        type="text"
        value={texto}
        onChange={(e) => { setTexto(e.target.value); setActivo(0); setAbierto(true); }}
        onFocus={() => setAbierto(true)}
        onKeyDown={teclas}
        placeholder={placeholder}
        autoComplete="off"
        role="combobox"
        aria-expanded={abierto && palabras.length > 0}
        aria-controls={idLista}
        aria-autocomplete="list"
        aria-activedescendant={visibles[activo] ? `${idLista}-${visibles[activo].id}` : undefined}
        // Obliga a elegir un socio antes de enviar el formulario.
        required={required}
        className={`${inputClassName} pl-9`}
      />
      {abierto && palabras.length > 0 && (
        <ul
          ref={lista}
          id={idLista}
          role="listbox"
          className="absolute z-20 mt-1 w-full max-h-72 overflow-y-auto bg-white border border-slate-200 rounded-xl shadow-lg py-1"
        >
          {visibles.length === 0 ? (
            <li className="px-3.5 py-3 text-xs text-slate-400">No hay socios activos con ese nombre.</li>
          ) : (
            visibles.map((s, i) => {
              const extra = nota?.(s);
              const repetido = repetidos[normalizar(s.nombre)] > 1;
              return (
                <li
                  key={s.id}
                  id={`${idLista}-${s.id}`}
                  data-indice={i}
                  role="option"
                  aria-selected={i === activo}
                  onMouseDown={(e) => { e.preventDefault(); elegir(s); }}
                  onMouseEnter={() => setActivo(i)}
                  className={`px-3.5 py-2 cursor-pointer text-sm ${i === activo ? "bg-emerald-50" : "hover:bg-slate-50"}`}
                >
                  <p className="font-semibold text-slate-800">{resaltar(s.nombre, palabras)}</p>
                  <p className={`text-[11px] flex flex-wrap items-center gap-x-2 ${repetido ? "text-amber-700 font-semibold" : "text-slate-400"}`}>
                    <span>ID {s.id}</span>
                    <span>CC {s.cedula}</span>
                    {s.residencia && <span className="inline-flex items-center gap-0.5"><MapPin className="w-3 h-3" />{s.residencia}</span>}
                    {extra && <span className="text-purple-600">{extra}</span>}
                  </p>
                </li>
              );
            })
          )}
          {resultados.length > MAX_RESULTADOS && (
            <li className="px-3.5 py-2 text-[11px] text-slate-400 border-t border-slate-100">
              Hay más coincidencias: escribe también el apellido para afinar la búsqueda.
            </li>
          )}
        </ul>
      )}
    </div>
  );
};
