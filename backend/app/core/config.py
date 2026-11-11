"""Configuración general de la aplicación con Pydantic Settings v2."""
import os
from pathlib import Path
from typing import List, Union, Literal
from urllib.parse import urlsplit
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    PROJECT_NAME: str = "Sistema de Gestión Natillera API"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False
    ENVIRONMENT: Literal["development", "test", "production"] = "production" if os.getenv("VERCEL") else "development"
    AUTO_CREATE_TABLES: bool = not bool(os.getenv("VERCEL"))
    DB_POOL_SIZE: int = Field(2, ge=1, le=10)
    DB_MAX_OVERFLOW: int = Field(0, ge=0, le=10)

    # Seguridad y JWT
    SECRET_KEY: str = ""
    ALGORITHM: Literal["HS256"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60, ge=1, le=480)

    # PostgreSQL
    DATABASE_URL: str

    # CORS
    BACKEND_CORS_ORIGINS: Union[str, List[str]] = "http://localhost:3000,http://localhost:5173,http://localhost:8000"

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        if len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY debe tener al menos 32 caracteres. Ejecuta python backend/setup_local.py para configurar el entorno local.")
        if make_url(self.DATABASE_URL).get_backend_name() != "postgresql":
            raise ValueError("DATABASE_URL debe usar PostgreSQL")
        for origin in self.cors_origins_list:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
                raise ValueError("CORS requiere orígenes exactos sin rutas ni comodines")
        if self.ENVIRONMENT == "production":
            if self.DEBUG or self.AUTO_CREATE_TABLES:
                raise ValueError("Producción requiere DEBUG=False y AUTO_CREATE_TABLES=False")
            if not self.cors_origins_list or any(not o.startswith("https://") for o in self.cors_origins_list):
                raise ValueError("Producción requiere orígenes CORS HTTPS explícitos")
            if make_url(self.DATABASE_URL).query.get("sslmode") not in {"require", "verify-full"}:
                raise ValueError("Producción requiere sslmode=require o verify-full")
            if "REEMPLAZAR" in self.SECRET_KEY or len(set(self.SECRET_KEY)) < 10:
                raise ValueError("Producción requiere una SECRET_KEY aleatoria")
        return self

    @property
    def cors_origins_list(self) -> List[str]:
        """Convierte la cadena de orígenes CORS separados por coma en una lista."""
        if isinstance(self.BACKEND_CORS_ORIGINS, str):
            return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]
        return self.BACKEND_CORS_ORIGINS

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        hide_input_in_errors=True,
        extra="ignore"
    )


settings = Settings()
