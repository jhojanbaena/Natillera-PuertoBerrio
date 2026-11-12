"""Contadores compartidos entre instancias serverless, sin guardar credenciales."""
from sqlalchemy import String, Integer, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, SCHEMA_COMUN


class LoginLimit(Base):
    __tablename__ = "login_limits"
    __table_args__ = {"schema": SCHEMA_COMUN}
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window: Mapped[int] = mapped_column(BigInteger, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
