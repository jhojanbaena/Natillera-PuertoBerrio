// Utilidades de formato monetario y fechas
export const formatMoney = (amount) => {
  if (amount === undefined || amount === null) return "$0";
  const num = typeof amount === "string" ? parseFloat(amount) : amount;
  return new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency: "COP",
    maximumFractionDigits: 0,
  }).format(num);
};

// Fecha "AAAA-MM-DD" en la zona horaria del equipo (para inputs type="date").
export const fechaLocalISO = (valor = new Date()) => {
  const d = valor instanceof Date ? valor : new Date(valor);
  if (Number.isNaN(d.getTime())) return "";
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};

export const formatDate = (dateStr) => {
  if (!dateStr) return "-";
  try {
    // "AAAA-MM-DD" se interpreta como UTC y en Colombia mostraría el día anterior.
    const soloFecha = /^\d{4}-\d{2}-\d{2}$/.exec(dateStr);
    const d = soloFecha ? new Date(`${dateStr}T00:00:00`) : new Date(dateStr);
    return d.toLocaleDateString("es-CO", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return dateStr;
  }
};
