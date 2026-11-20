import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { LogOut, ZoomIn, ZoomOut } from "lucide-react";
import { cerrarSesionSocio, leerTokenSocio, obtenerMiHoja } from "../api/socioClient";
import { construirHoja } from "../utils/hojaAhorro";

// Ancho de la hoja impresa (apaisada). En pantallas más angostas se reduce a escala
// para verla completa, sin cambiar su diseño.
const ANCHO_HOJA = 1120;

// Vista del socio: solo su ficha de Total ahorrado (la misma del botón Imprimir) y
// el botón de cerrar sesión. Independiente del panel administrativo y sin menú.
export const PortalSocio = () => {
  const navigate = useNavigate();
  const [hoja, setHoja] = useState(null);
  const [error, setError] = useState("");
  const [escala, setEscala] = useState(1);
  const [ampliada, setAmpliada] = useState(false);
  const [alto, setAlto] = useState(800);
  const contenedor = useRef(null);
  const marco = useRef(null);
  const token = leerTokenSocio();

  const salir = useCallback((aviso) => {
    cerrarSesionSocio(aviso);
    navigate("/login?socio", { replace: true });
  }, [navigate]);

  useEffect(() => {
    if (!token) return undefined;
    const cargar = () => obtenerMiHoja()
      .then((datos) => {
        setHoja(datos);
        setError("");
      })
      .catch((err) => {
        const detalle = err.response?.data?.detail;
        if (err.response?.status === 401 || err.response?.status === 403) {
          salir(typeof detalle === "string" ? detalle : "Tu sesión terminó; vuelve a ingresar");
          return;
        }
        setError("No se pudo cargar tu ficha. Revisa tu conexión e inténtalo de nuevo.");
      });
    cargar();
    // Si el Desarrollador quita el acceso, la hoja deja de verse aunque la página siga abierta.
    const intervalo = setInterval(cargar, 60000);
    const alVolver = () => {
      if (document.visibilityState === "visible") cargar();
    };
    document.addEventListener("visibilitychange", alVolver);
    return () => {
      clearInterval(intervalo);
      document.removeEventListener("visibilitychange", alVolver);
    };
  }, [token, salir]);

  // Escala de la hoja según el ancho disponible.
  useLayoutEffect(() => {
    const el = contenedor.current;
    if (!el) return undefined;
    const medir = () => setEscala(Math.min(1, el.clientWidth / ANCHO_HOJA));
    medir();
    const observador = new ResizeObserver(medir);
    observador.observe(el);
    return () => observador.disconnect();
  }, [hoja]);

  const ajustarAlto = () => {
    // Alto real del contenido (el del documento nunca es menor que el del marco).
    const cuerpo = marco.current?.contentDocument?.body;
    if (cuerpo) setAlto(Math.ceil(cuerpo.getBoundingClientRect().height));
  };

  if (!token) return <Navigate to="/login?socio" replace />;

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col">
      <header className="bg-white border-b border-slate-200 px-4 py-3 flex items-center gap-3 sticky top-0 z-10">
        <img src="/logo-natillera.jpg" alt="" className="w-9 h-9 rounded-full object-cover" />
        <div className="flex-1 min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-wider text-purple-700">Natillera Puerto Berrío</p>
          <p className="text-sm font-bold text-slate-800 truncate">{hoja ? hoja.socio.nombre : "Mi ahorro"}</p>
        </div>
        <button
          type="button"
          onClick={() => salir()}
          className="shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-xl bg-rose-50 text-rose-700 text-sm font-bold border border-rose-200 hover:bg-rose-100 transition-colors"
        >
          <LogOut className="w-4 h-4" />
          Cerrar sesión
        </button>
      </header>

      <main className="flex-1 w-full max-w-[1160px] mx-auto p-4">
        {error && (
          <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-sm">{error}</div>
        )}
        {!hoja && !error && (
          <div className="flex justify-center py-20">
            <div className="w-10 h-10 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
          </div>
        )}
        {hoja && (
          <div ref={contenedor} className="w-full">
            {escala < 1 && (
              <div className="flex justify-end mb-2">
                <button
                  type="button"
                  onClick={() => setAmpliada((v) => !v)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-700 text-xs font-bold shadow-sm"
                >
                  {ampliada ? <ZoomOut className="w-4 h-4" /> : <ZoomIn className="w-4 h-4" />}
                  {ampliada ? "Ajustar a la pantalla" : "Ampliar"}
                </button>
              </div>
            )}
            <div
              className={`bg-white rounded-xl shadow-sm ${ampliada ? "overflow-x-auto" : "overflow-hidden"}`}
              style={{ height: alto * (ampliada ? 1 : escala) }}
            >
              <iframe
                ref={marco}
                title="Total ahorrado"
                // Sin scripts: la hoja es HTML estático (con sus textos escapados).
                sandbox="allow-same-origin"
                srcDoc={construirHoja(hoja, `${window.location.origin}/logo-natillera.jpg`)}
                onLoad={ajustarAlto}
                scrolling="no"
                style={{
                  width: ANCHO_HOJA,
                  height: alto,
                  border: 0,
                  transform: `scale(${ampliada ? 1 : escala})`,
                  transformOrigin: "top left",
                }}
              />
            </div>
          </div>
        )}
      </main>
    </div>
  );
};
