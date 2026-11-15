import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { 
  LayoutDashboard, 
  Users, 
  BadgePercent, 
  CalendarDays, 
  Sparkles, 
  History,
  HandHeart,
  Receipt,
  Scale,
  CalendarRange,
  LogOut, 
  X 
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { usePeriodo } from "../context/PeriodoContext";

export const Sidebar = ({ isOpen, onClose }) => {
  const { user, logout } = useAuth();
  const { periodo } = usePeriodo();
  const navigate = useNavigate();

  const navItems = [
    { to: "/", label: "Dashboard", icon: LayoutDashboard },
    { to: "/socios", label: "Socios", icon: Users },
    { to: "/prestamos", label: "Préstamos y Cartera", icon: BadgePercent },
    { to: "/actividades-rifas", label: "Eventos y Rifas", icon: CalendarDays },
    { to: "/liquidacion", label: "Liquidación Anual", icon: Sparkles },
    { to: "/historial", label: "Historial de Movimientos", icon: History },
    { to: "/bien-comun", label: "Bien Común", icon: HandHeart },
    { to: "/gastos-generales", label: "Gastos Generales", icon: Receipt },
    { to: "/contabilidad", label: "Contabilidad", icon: Scale },
  ];

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div 
          onClick={onClose} 
          className="fixed inset-0 z-40 bg-slate-900/50 backdrop-blur-sm md:hidden"
        />
      )}

      <aside 
        className={`fixed top-0 left-0 z-40 h-screen w-64 bg-white border-r border-slate-200/80 flex flex-col transition-transform duration-300 ease-in-out md:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Brand header */}
        <div className="flex items-center justify-between px-6 h-18 border-b border-slate-100">
          <div className="flex items-center gap-3 py-4">
            <img
              src="/logo-natillera.jpg"
              alt="Logo Natillera Puerto Berrío"
              className="w-11 h-11 shrink-0 rounded-full object-cover shadow-md shadow-purple-500/20"
            />
            <div>
              <h1 className="font-bold text-purple-800 text-base leading-tight">Natillera Puerto Berrío</h1>
              <span className="text-[11px] font-semibold text-purple-600 uppercase tracking-wider">Gestión Integral</span>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="md:hidden p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Nav Links */}
        <nav className="flex-1 px-4 py-6 space-y-1.5 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => onClose && onClose()}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3.5 py-3 rounded-xl font-medium text-sm transition-all ${
                    isActive
                      ? "bg-emerald-50 text-emerald-700 font-semibold shadow-xs"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  }`
                }
              >
                <Icon className="w-5 h-5" />
                {item.label}
              </NavLink>
            );
          })}
        </nav>

        {/* Años: historial de periodos y creación de un año nuevo */}
        <div className="px-4 pb-3">
          <NavLink
            to="/anios"
            onClick={() => onClose && onClose()}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3.5 py-3 rounded-xl font-medium text-sm transition-all ${
                isActive
                  ? "bg-emerald-50 text-emerald-700 font-semibold shadow-xs"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            <CalendarRange className="w-5 h-5" />
            Años
            {periodo?.anio_consultado && (
              <span
                className={`ml-auto px-2 py-0.5 rounded-full text-[10px] font-bold ${
                  periodo.solo_lectura ? "bg-amber-100 text-amber-800" : "bg-purple-100 text-purple-800"
                }`}
              >
                {periodo.anio_consultado}
              </span>
            )}
          </NavLink>
        </div>

        {/* User Card & Logout */}
        <div className="p-4 border-t border-slate-100 bg-slate-50/50">
          <div className="flex items-center justify-between mb-3">
            <div className="overflow-hidden">
              <p className="text-sm font-bold text-slate-800 truncate">
                {user?.nombre_completo || user?.username || "Administrador"}
              </p>
              <p className="text-xs text-slate-500 truncate">@{user?.username}</p>
            </div>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
              {user?.is_admin ? "ADMIN" : "SOCIO"}
            </span>
          </div>
          <button
            onClick={handleLogout}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 text-xs font-semibold text-rose-600 bg-rose-50 hover:bg-rose-100 rounded-lg transition-colors"
          >
            <LogOut className="w-4 h-4" />
            Cerrar Sesión
          </button>
        </div>
      </aside>
    </>
  );
};
