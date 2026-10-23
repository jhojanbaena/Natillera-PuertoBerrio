"""Punto de entrada principal de la aplicación FastAPI.
Configura middlewares CORS, ciclo de vida (creación de tablas) y registro de todos los routers.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import Base, engine, ensure_compatibility_columns
import app.models  # Registra todos los modelos en Base.metadata
from app.routers import (
    auth_router,
    socios_router,
    actividades_router,
    rifas_router,
    reuniones_router,
    notas_router,
    prestamos_router,
    programacion_router,
    dashboard_router,
    historial_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Crear tablas automáticamente al iniciar si no existen
    if settings.AUTO_CREATE_TABLES:
        Base.metadata.create_all(bind=engine)
        ensure_compatibility_columns()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="API RESTful para la gestión integral de una Natillera (Ahorro, Crédito, Sorteos y Eventos Comunitarios).",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "La operación viola una restricción de integridad o un registro ya existe"})


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response

# Lista completa de routers
all_routers = [
    auth_router,
    socios_router,
    actividades_router,
    rifas_router,
    reuniones_router,
    notas_router,
    prestamos_router,
    programacion_router,
    dashboard_router,
    historial_router,
]

# Inclusión con y sin prefijo para máxima versatilidad
for r in all_routers:
    app.include_router(r, prefix=settings.API_V1_STR)
    app.include_router(r)


@app.get("/", tags=["Estado"])
def root():
    return {
        "status": "online",
        "project": settings.PROJECT_NAME,
        "docs": "/docs",
        "api_v1": settings.API_V1_STR,
    }
