"""Modelo de notificaciones de RescueSync."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensiones import db

if TYPE_CHECKING:
    from app.modulos.organizaciones.modelos import Organizacion


class Notificacion(db.Model):
    """Aviso compartido por los usuarios de una organización."""

    __tablename__ = "notificacion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organizacion_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizacion.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    enlace: Mapped[str] = mapped_column(String(500), nullable=False)
    leida: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    organizacion: Mapped[Organizacion] = relationship("Organizacion", lazy="select")

    def __repr__(self) -> str:
        return (
            f"<Notificacion id={self.id} organizacion_id={self.organizacion_id} "
            f"leida={self.leida}>"
        )
