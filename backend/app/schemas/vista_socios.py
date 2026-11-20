"""Esquemas de "Permitir vista a los socios" y del portal de socios."""
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class VistaSociosUpdate(BaseModel):
    modo: Literal["TODOS", "RANGO", "DESACTIVADO"]
    id_inicio: Optional[int] = Field(None, ge=1, le=2_147_483_647)
    id_fin: Optional[int] = Field(None, ge=1, le=2_147_483_647)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validar_rango(self) -> "VistaSociosUpdate":
        if self.modo == "RANGO":
            if self.id_inicio is None or self.id_fin is None:
                raise ValueError("Indica el ID inicial y el ID final del rango")
            if self.id_fin < self.id_inicio:
                raise ValueError("El ID final debe ser mayor o igual al ID inicial")
        else:
            self.id_inicio = None
            self.id_fin = None
        return self


class VistaSociosResponse(BaseModel):
    modo: str
    id_inicio: Optional[int] = None
    id_fin: Optional[int] = None
    actualizado_por: Optional[str] = None
    actualizado_en: Optional[datetime] = None
    socios_con_acceso: int = 0
    socios_bloqueados: int = 0


class SocioLogin(BaseModel):
    """Usuario y contraseña son la cédula registrada, solo números."""
    username: str = Field(..., min_length=1, max_length=20)
    password: str = Field(..., min_length=1, max_length=20)

    model_config = ConfigDict(extra="forbid")
