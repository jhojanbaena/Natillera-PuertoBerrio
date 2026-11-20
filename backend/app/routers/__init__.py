"""Módulo de Routers y Endpoints de la API."""
from app.routers.auth import router as auth_router
from app.routers.socios import router as socios_router
from app.routers.actividades import router as actividades_router
from app.routers.rifas import router as rifas_router
from app.routers.reuniones import router as reuniones_router
from app.routers.notas import router as notas_router
from app.routers.prestamos import router as prestamos_router
from app.routers.programacion import router as programacion_router
from app.routers.dashboard import router as dashboard_router
from app.routers.historial import router as historial_router
from app.routers.liquidacion_pagos import router as liquidacion_pagos_router
from app.routers.gastos_generales import router as gastos_generales_router
from app.routers.contabilidad import router as contabilidad_router
from app.routers.periodos import router as periodos_router
from app.routers.estadisticas import router as estadisticas_router
from app.routers.panel import router as panel_router
from app.routers.portal_socio import router as portal_socio_router

__all__ = [
    "auth_router",
    "socios_router",
    "actividades_router",
    "rifas_router",
    "reuniones_router",
    "notas_router",
    "prestamos_router",
    "programacion_router",
    "dashboard_router",
    "historial_router",
    "liquidacion_pagos_router",
    "gastos_generales_router",
    "contabilidad_router",
    "periodos_router",
    "estadisticas_router",
    "panel_router",
    "portal_socio_router",
]
