"""Modelos del módulo de ofertas colaborativas de RescueSync.

Implementa el eslabón 3 del enunciado del TP:
Las ONGs presentan ofertas de ayuda durante la ventana temporal de la convocatoria,
especificando ítems y cantidades. Permite que múltiples organizaciones formen
consorcios colaborativos mediante la tabla asociativa `oferta_organizacion`.
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
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensiones import db

if TYPE_CHECKING:
    # from app.modulos.adjudicaciones.modelos import Adjudicacion
    from app.modulos.convocatorias.modelos import Convocatoria
    from app.modulos.emergencias.modelos import LoteItem
    from app.modulos.organizaciones.modelos import Organizacion
    from app.modulos.usuarios_roles.modelos import Usuario


class EstadoOferta(enum.Enum):
    """Estado de la oferta en su ciclo de vida."""

    pendiente = "pendiente"
    presentada = "presentada"
    retirada = "retirada"
    adjudicada = "adjudicada"
    rechazada = "rechazada"


class Oferta(db.Model):
    """Oferta presentada por una o más ONGs (consorcio) para una convocatoria activa."""

    __tablename__ = "oferta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    convocatoria_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("convocatoria.id"),
        nullable=False,
        index=True,
    )
    usuario_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("usuarios.id"),
        nullable=False,
        comment="Usuario que carga o gestiona la oferta en representación del consorcio.",
    )

    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="Número secuencial de versión incrementado en cada modificación.",
    )
    estado: Mapped[EstadoOferta] = mapped_column(
        Enum(EstadoOferta, name="estado_oferta_enum"),
        default=EstadoOferta.presentada,
        nullable=False,
    )
    observaciones: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Notas sobre logística, plazos de entrega o disponibilidad.",
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
    convocatoria: Mapped[Convocatoria] = relationship(
        "Convocatoria",
        back_populates="ofertas",
    )
    usuario: Mapped[Usuario] = relationship("Usuario", lazy="select")

    # Consorcio de organizaciones participantes (M:N con atributo de rol)
    organizaciones_consorcio: Mapped[list[OfertaOrganizacion]] = relationship(
        "OfertaOrganizacion",
        back_populates="oferta",
        lazy="selectin",
    )

    items: Mapped[list[OfertaLinea]] = relationship(
        "OfertaLinea",
        back_populates="oferta",
        lazy="select",
    )
    # adjudicaciones: Mapped[list[Adjudicacion]] = relationship(
    #     "Adjudicacion",
    #     back_populates="oferta",
    #     lazy="select",
    # )

    versiones: Mapped[list[OfertaVersion]] = relationship(
        "OfertaVersion",
        back_populates="oferta",
        lazy="select",
        order_by="OfertaVersion.version.asc()",
    )

    @property
    def organizacion_lider(self) -> Organizacion | None:
        """Devuelve la organización líder del consorcio si existe."""
        for miembro in self.organizaciones_consorcio:
            if miembro.rol_consorcio.lower() == "lider":
                return miembro.organizacion
        return (
            self.organizaciones_consorcio[0].organizacion if self.organizaciones_consorcio else None
        )

    @property
    def organizacion(self) -> Organizacion | None:
        """Devuelve la organización de la oferta simple."""
        return self.organizacion_lider

    def puede_modificarse(self) -> bool:
        """Una oferta solo puede modificarse si la convocatoria está vigente y activa."""
        return self.convocatoria.esta_vigente() and self.estado not in (
            EstadoOferta.retirada,
            EstadoOferta.rechazada,
            EstadoOferta.adjudicada,
        )

    def __repr__(self) -> str:
        return f"<Oferta id={self.id} version={self.version} estado={self.estado.value}>"


class OfertaOrganizacion(db.Model):
    """Asociación de organizaciones en consorcio para una oferta colaborativa."""

    __tablename__ = "oferta_organizacion"

    oferta_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("oferta.id", ondelete="CASCADE"),
        primary_key=True,
    )
    organizacion_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizacion.id", ondelete="CASCADE"),
        primary_key=True,
    )

    rol_consorcio: Mapped[str] = mapped_column(
        String(50),
        default="miembro",
        nullable=False,
        comment="Rol en el consorcio: 'lider', 'aportante', 'logistica', 'coordinador', etc.",
    )
    estado_participacion: Mapped[str] = mapped_column(
        String(20),
        default="pendiente",
        nullable=False,
        comment="Estado de la invitación: 'pendiente' o 'aceptada'.",
    )

    # --- relaciones -----------------------------------------------------------
    oferta: Mapped[Oferta] = relationship("Oferta", back_populates="organizaciones_consorcio")
    organizacion: Mapped[Organizacion] = relationship("Organizacion", lazy="select")

    def __repr__(self) -> str:
        return (
            f"<OfertaOrganizacion oferta_id={self.oferta_id} "
            f"organizacion_id={self.organizacion_id} rol={self.rol_consorcio!r}>"
        )


class OfertaLinea(db.Model):
    """Ítem específico dentro de una oferta de ayuda con cantidad ofrecida."""

    __tablename__ = "oferta_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    oferta_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("oferta.id"),
        nullable=False,
        index=True,
    )
    lote_item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lote_item.id"),
        nullable=False,
        index=True,
    )
    organizacion_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizacion.id"),
        nullable=False,
        index=True,
        comment="ONG responsable de esta línea dentro de la oferta conjunta.",
    )

    cantidad_ofrecida: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Cantidad que la ONG se compromete a aportar para este ítem del lote.",
    )
    observaciones: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- relaciones -----------------------------------------------------------
    oferta: Mapped[Oferta] = relationship("Oferta", back_populates="items")
    lote_item: Mapped[LoteItem] = relationship("LoteItem", lazy="select")
    organizacion: Mapped[Organizacion] = relationship("Organizacion", lazy="select")

    def __repr__(self) -> str:
        return (
            f"<OfertaLinea id={self.id} oferta_id={self.oferta_id} "
            f"lote_item_id={self.lote_item_id} cant={self.cantidad_ofrecida}>"
        )


class OfertaVersion(db.Model):
    """Snapshot histórico de una oferta antes de ser modificada.

    Cada vez que una ONG modifica su oferta, se guarda una foto del estado
    previo (cabecera + líneas serializadas como JSON) para mantener la
    trazabilidad exigida por el enunciado de la Entrega 2.
    """

    __tablename__ = "oferta_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    oferta_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("oferta.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Número de versión que se está reemplazando.",
    )
    estado_anterior: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Estado de la oferta antes de la modificación.",
    )
    observaciones_anteriores: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    items_snapshot: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="JSON con las líneas de la oferta previas a la modificación.",
    )
    modificado_por: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("usuarios.id"),
        nullable=True,
        comment="Usuario que realizó la modificación.",
    )
    registrado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # --- relaciones -----------------------------------------------------------
    oferta: Mapped[Oferta] = relationship("Oferta", back_populates="versiones")

    def __repr__(self) -> str:
        return (
            f"<OfertaVersion id={self.id} oferta_id={self.oferta_id} "
            f"version={self.version}>"
        )
