import React, { useLayoutEffect, useRef } from "react";

// Campo monetario con puntos como separadores de miles (2000000 -> 2.000.000).
// - Lo que se ve lleva puntos; el valor que se entrega en onChange es el número
//   "crudo" ("2000000" o "2000000.5"), así los cálculos y lo que se guarda en la
//   base de datos no cambian.
// - La coma es el separador decimal (máximo 2 decimales).
// - onChange recibe un objeto { target: { value } }, igual que un <input>, para
//   reemplazar campos type="number" sin cambiar sus manejadores.

/** "1.500.000,5" -> "1500000.5" (valor numérico en texto, sin separadores). */
export const aNumeroCrudo = (texto) => {
  const limpio = String(texto ?? "").replace(/[^\d,]/g, "");
  if (!limpio) return "";
  const [enteroTxt, ...resto] = limpio.split(",");
  const entero = enteroTxt.replace(/^0+(?=\d)/, "") || (resto.length ? "0" : "");
  if (!resto.length) return entero;
  return `${entero}.${resto.join("").slice(0, 2)}`;
};

/** "1500000.5" o 1500000.5 -> "1.500.000,5" (para mostrar en el campo). */
export const formatearMiles = (valor) => {
  if (valor === null || valor === undefined || valor === "") return "";
  const texto = String(valor);
  if (!/^-?\d*(\.\d*)?$/.test(texto)) return texto;
  const negativo = texto.startsWith("-");
  const [entero = "", decimales] = texto.replace("-", "").split(".");
  const conPuntos = (entero.replace(/^0+(?=\d)/, "") || (decimales !== undefined ? "0" : ""))
    .replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  // Los valores guardados llegan como "70000.00": no mostrar ",00".
  const dec = decimales === undefined || /^0{2,}$/.test(decimales) ? null : decimales.slice(0, 2);
  return `${negativo ? "-" : ""}${conPuntos}${dec !== null ? `,${dec}` : ""}`;
};

export const MoneyInput = React.forwardRef(function MoneyInput(
  { value, onChange, name, step: _step, min: _min, max: _max, type: _type, ...props },
  refExterno,
) {
  const ref = useRef(null);
  const posicion = useRef(null);
  const mostrado = formatearMiles(value);

  // Conservar el cursor en su lugar aunque se agreguen o quiten puntos.
  useLayoutEffect(() => {
    const el = ref.current;
    if (posicion.current === null || !el || document.activeElement !== el) return;
    const objetivo = posicion.current;
    posicion.current = null;
    let vistos = 0;
    let i = 0;
    while (i < el.value.length && vistos < objetivo) {
      if (/[\d,]/.test(el.value[i])) vistos += 1;
      i += 1;
    }
    el.setSelectionRange(i, i);
  });

  const manejarCambio = (e) => {
    const texto = e.target.value;
    const cursor = e.target.selectionStart ?? texto.length;
    posicion.current = texto.slice(0, cursor).replace(/[^\d,]/g, "").length;
    onChange?.({ target: { value: aNumeroCrudo(texto), name } });
  };

  const asignarRef = (nodo) => {
    ref.current = nodo;
    if (typeof refExterno === "function") refExterno(nodo);
    else if (refExterno) refExterno.current = nodo;
  };

  return (
    <input
      {...props}
      ref={asignarRef}
      name={name}
      type="text"
      inputMode="decimal"
      autoComplete="off"
      value={mostrado}
      onChange={manejarCambio}
    />
  );
});
