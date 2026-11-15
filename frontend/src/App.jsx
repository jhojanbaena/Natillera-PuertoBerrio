import React, { useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { PeriodoProvider, usePeriodo } from "./context/PeriodoContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Sidebar } from "./components/Sidebar";
import { Navbar } from "./components/Navbar";
import { Login } from "./pages/Login";
import { Dashboard } from "./pages/Dashboard";
import { Socios } from "./pages/Socios";
import { Prestamos } from "./pages/Prestamos";
import { ActividadesRifas } from "./pages/ActividadesRifas";
import { Liquidacion } from "./pages/Liquidacion";
import { Historial } from "./pages/Historial";
import { BienComun } from "./pages/BienComun";
import { GastosGenerales } from "./pages/GastosGenerales";
import { Contabilidad } from "./pages/Contabilidad";
import { Anios } from "./pages/Anios";
import { Estadisticas } from "./pages/Estadisticas";
import { Panel } from "./pages/Panel";
import { Lock } from "lucide-react";

const pageTitles = {
  "/": "Dashboard — Lobby Financiero",
  "/socios": "Socios y Estado de Cuenta",
  "/prestamos": "Préstamos y Cartera",
  "/actividades-rifas": "Eventos, Rifas y Reuniones",
  "/liquidacion": "Liquidación Anual y Utilidades",
  "/historial": "Historial Global de Movimientos",
  "/bien-comun": "Bien Común",
  "/gastos-generales": "Gastos Generales",
  "/contabilidad": "Contabilidad",
  "/anios": "Años de la Natillera",
  "/estadisticas": "Estadísticas de Movimientos",
  "/panel": "Panel del Desarrollador",
};

const Layout = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const path = window.location.pathname;
  const title = pageTitles[path] || "Natillera Puerto Berrío";
  const { periodo, listo, volverAlActivo } = usePeriodo();

  if (!listo) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="w-10 h-10 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex flex-col flex-1 md:pl-64 min-w-0">
        <Navbar
          onOpenSidebar={() => setSidebarOpen(true)}
          title={title}
        />
        <main className="flex-1 p-4 md:p-8 max-w-7xl w-full mx-auto">
          {periodo?.solo_lectura && (
            <div className="mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-2xl bg-amber-50 border border-amber-200 text-amber-900">
              <p className="flex items-start gap-2 text-sm font-medium">
                <Lock className="w-4 h-4 shrink-0 mt-0.5" />
                <span>
                  Estás consultando el año <strong>{periodo.anio_consultado}</strong>. Es de solo consulta: no se pueden registrar ni modificar datos.
                </span>
              </p>
              <button
                onClick={volverAlActivo}
                className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-bold text-white bg-amber-600 hover:bg-amber-700 transition-colors"
              >
                Volver al año activo {periodo.anio_activo}
              </button>
            </div>
          )}
          {children}
        </main>
        <footer className="text-center py-4 text-[11px] text-slate-400 border-t border-slate-200/80">
          Natillera Puerto Berrío · Backend: FastAPI + SQLAlchemy · Frontend: React + Tailwind CSS
        </footer>
      </div>
    </div>
  );
};

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <PeriodoProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Layout><Dashboard /></Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/socios"
            element={
              <ProtectedRoute>
                <Layout><Socios /></Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/prestamos"
            element={
              <ProtectedRoute>
                <Layout><Prestamos /></Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/actividades-rifas"
            element={
              <ProtectedRoute>
                <Layout><ActividadesRifas /></Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/liquidacion"
            element={
              <ProtectedRoute>
                <Layout><Liquidacion /></Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/historial"
            element={
              <ProtectedRoute>
                <Layout><Historial /></Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/bien-comun"
            element={
              <ProtectedRoute>
                <Layout><BienComun /></Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/gastos-generales"
            element={
              <ProtectedRoute>
                <Layout><GastosGenerales /></Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/contabilidad"
            element={
              <ProtectedRoute>
                <Layout><Contabilidad /></Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/anios"
            element={
              <ProtectedRoute>
                <Layout><Anios /></Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/estadisticas"
            element={
              <ProtectedRoute>
                <Layout><Estadisticas /></Layout>
              </ProtectedRoute>
            }
          />
          {/* Exclusivo del rol Desarrollador */}
          <Route
            path="/panel"
            element={
              <ProtectedRoute soloDesarrollador>
                <Layout><Panel /></Layout>
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </PeriodoProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
