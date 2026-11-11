"""Modelos del módulo de ejecución y cierre de RescueSync.

Implementa el seguimiento local de ejecución de las ONGs adjudicadas (Etapa 7).
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensiones import db

if TYPE_CHECKING:
    from app.modulos.emergencias.modelos import Emergencia
    from app.modulos.ofertas.modelos import Oferta
    from app.modulos.organizaciones.modelos import Organizacion
    from app.modulos.usuarios_roles.modelos import Usuario


class EstadoTareaEjecucion(enum.Enum):
    """Estado de ejecución de una tarea adjudicada a una ONG."""

    en_progreso = "en_progreso"
    cierre_pendiente = "cierre_pendiente"
    finalizada = "finalizada"
    cancelada = "cancelada"


class TareaEjecucion(db.Model):
    """Seguimiento de la ejecución de una oferta adjudicada a una ONG."""

    __tablename__ = "ejecucion_tarea"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    emergencia_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("emergencia.id"),
        nullable=False,
        index=True,
        comment="Emergencia a la que responde la tarea.",
    )
    oferta_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("oferta.id"),
        nullable=False,
        index=True,
        comment="Oferta adjudicada que dio origen a la tarea.",
    )
    organizacion_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizacion.id"),
        nullable=False,
        index=True,
        comment="ONG responsable de la ejecución de esta tarea.",
    )

    estado: Mapped[EstadoTareaEjecucion] = mapped_column(
        Enum(EstadoTareaEjecucion, name="estado_tarea_ejecucion_enum"),
        default=EstadoTareaEjecucion.en_progreso,
        nullable=False,
        comment="Estado actual del despliegue en campo.",
    )

    fecha_inicio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Fecha en que se adjudicó e inició la tarea.",
    )
    fecha_fin: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Fecha en que la ONG marcó la tarea como terminada.",
    )

    usuario_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("usuarios.id"),
        nullable=True,
        comment="Usuario representante de la ONG que marcó la finalización.",
    )
    observaciones: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Notas o informe final de cierre provisto por la ONG.",
    )

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # --- relaciones -----------------------------------------------------------
    emergencia: Mapped[Emergencia] = relationship("Emergencia", lazy="joined")
    oferta: Mapped[Oferta] = relationship("Oferta", lazy="joined")
    organizacion: Mapped[Organizacion] = relationship("Organizacion", lazy="joined")
    usuario: Mapped[Usuario | None] = relationship("Usuario", lazy="select")

    def __init__(
        self,
        *,
        emergencia_id: int,
        oferta_id: int,
        organizacion_id: int,
        estado: EstadoTareaEjecucion = EstadoTareaEjecucion.en_progreso,
        usuario_id: int | None = None,
        observaciones: str | None = None,
    ) -> None:
        self.emergencia_id = emergencia_id
        self.oferta_id = oferta_id
        self.organizacion_id = organizacion_id
        self.estado = estado
        self.usuario_id = usuario_id
        self.observaciones = observaciones

    def __repr__(self) -> str:
        return (
            f"<TareaEjecucion id={self.id} oferta_id={self.oferta_id} "
            f"ong_id={self.organizacion_id} estado={self.estado.value}>"
        )
