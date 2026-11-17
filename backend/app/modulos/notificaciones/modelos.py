"""Modelo de notificaciones de RescueSync."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.identificadores import nuevo_id
from app.extensiones import db

if TYPE_CHECKING:
    from app.modulos.organizaciones.modelos import Organizacion


class Notificacion(db.Model):
    """Aviso compartido por los usuarios de una organización."""

    __tablename__ = "notificacion"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
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
            f"<Notificacion id={self.id} organizacion_id={self.organizacion_id} leida={self.leida}>"
        )
