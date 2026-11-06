"""Modelos del módulo de convocatorias de RescueSync.

Implementa la apertura de convocatorias por parte del Coordinador Regional
para atender una emergencia activa, estableciendo una ventana temporal (fecha inicio y fecha fin)
durante la cual las ONGs pueden postular sus ofertas colaborativas.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensiones import db

if TYPE_CHECKING:
    from app.modulos.emergencias.modelos import Emergencia, LoteNecesidad
    from app.modulos.ofertas.modelos import Oferta
    from app.modulos.usuarios_roles.modelos import Usuario


class EstadoConvocatoria(enum.Enum):
    """Estado de la convocatoria en el ciclo de vida de la asignación."""

    borrador = "borrador"
    abierta = "abierta"
    cerrada = "cerrada"
    adjudicada = "adjudicada"
    cancelada = "cancelada"


class Convocatoria(db.Model):
    """Convocatoria publicada para atender una emergencia."""

    __tablename__ = "convocatoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    emergencia_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("emergencia.id"),
        nullable=False,
        index=True,
    )

    # Coordinador regional que publica la convocatoria
    # No esta en el diagrama pero considero que no esta de mas
    coordinador_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("usuarios.id"),
        nullable=False,
    )

    fecha_inicio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Inicio de la ventana temporal para presentar ofertas.",
    )
    fecha_cierre: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment=(
            "Fin de la ventana temporal. Pasada esta fecha no se admiten ofertas ni modificaciones."
        ),
    )

    resumen_situacion: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Resumen de la situación publicado junto con la convocatoria.",
    )

    estado: Mapped[EstadoConvocatoria] = mapped_column(
        Enum(EstadoConvocatoria, name="estado_convocatoria_enum"),
        default=EstadoConvocatoria.abierta,
        nullable=False,
    )

    observaciones: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Instrucciones adicionales o requisitos de entrega.",
    )

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    cobertura_completa: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Indica si el Sistema Nacional cubrió efectivamente todas las necesidades.",
    )
    cobertura_evaluada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # --- relaciones -----------------------------------------------------------
    emergencia: Mapped[Emergencia] = relationship(
        "Emergencia",
        back_populates="convocatorias",
    )
    coordinador: Mapped[Usuario] = relationship("Usuario", lazy="select")
    ofertas: Mapped[list[Oferta]] = relationship(
        "Oferta",
        back_populates="convocatoria",
        lazy="select",
    )
    lotes: Mapped[list[LoteNecesidad]] = relationship(
        "LoteNecesidad",
        back_populates="convocatoria",
        lazy="select",
    )

    def esta_vigente(self) -> bool:
        """Verifica si la convocatoria está en estado abierta y dentro de la ventana temporal."""
        if self.fecha_inicio.tzinfo is not None:
            ahora = datetime.now(self.fecha_inicio.tzinfo)
        else:
            ahora = datetime.now(UTC).replace(tzinfo=None)
        return (
            self.estado == EstadoConvocatoria.abierta
            and self.fecha_inicio <= ahora <= self.fecha_cierre
        )

    def __repr__(self) -> str:
        return (
            f"<Convocatoria id={self.id} emergencia_id={self.emergencia_id} "
            f"estado={self.estado.value}>"
        )
