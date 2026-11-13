"""Esquemas de validación Pydantic para Autenticación y Usuarios."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class UsuarioBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Nombre de usuario único")
    nombre_completo: Optional[str] = Field(None, max_length=100, description="Nombre y apellido")
    is_admin: bool = Field(False, description="Indica si tiene permisos de administrador")


class UsuarioCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Nombre de usuario único")
    nombre_completo: Optional[str] = Field(None, max_length=100, description="Nombre y apellido")
    password: str = Field(..., min_length=12, max_length=72, description="Contraseña en texto plano para registro")

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("La contraseña no puede superar 72 bytes UTF-8")
        return value

    model_config = ConfigDict(extra="forbid")


class UsuarioLogin(BaseModel):
    username: str = Field(..., min_length=1, max_length=50, description="Nombre de usuario")
    password: str = Field(..., min_length=1, max_length=256, description="Contraseña")


class UsuarioResponse(UsuarioBase):
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None
