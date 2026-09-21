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
    Numeric,
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

    presentada = "presentada"
    modificada = "modificada"
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

    @property
    def organizacion_lider(self) -> Organizacion | None:
        """Devuelve la organización líder del consorcio si existe."""
        for miembro in self.organizaciones_consorcio:
            if miembro.rol_consorcio.lower() == "lider":
                return miembro.organizacion
        return (
            self.organizaciones_consorcio[0].organizacion if self.organizaciones_consorcio else None
        )

    def puede_modificarse(self) -> bool:
        """Una oferta solo puede modificarse si la convocatoria está vigente y no fue retirada."""
        return self.convocatoria.esta_vigente() and self.estado != EstadoOferta.retirada

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

    cantidad_ofrecida: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Cantidad que la ONG se compromete a aportar para este ítem del lote.",
    )
    observaciones: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- relaciones -----------------------------------------------------------
    oferta: Mapped[Oferta] = relationship("Oferta", back_populates="items")
    lote_item: Mapped[LoteItem] = relationship("LoteItem", lazy="select")

    def __repr__(self) -> str:
        return (
            f"<OfertaLinea id={self.id} oferta_id={self.oferta_id} "
            f"lote_item_id={self.lote_item_id} cant={self.cantidad_ofrecida}>"
        )
