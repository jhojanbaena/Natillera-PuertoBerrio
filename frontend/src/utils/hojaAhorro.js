// Hoja de "Total ahorrado" del socio (estilo de la planilla en papel).
// La usan el botón Imprimir del apartado Socios y la vista de los socios.
import { formatMoney } from "./formatters";

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

export const construirHoja = (h, logoUrl) => {
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
