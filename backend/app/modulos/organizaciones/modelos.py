"""Modelos de municipios y organizaciones de RescueSync.

Una organizacion representa a una entidad externa que participa en el sistema.
Existen tres tipos principales según el enunciado:
  - municipio: municipio afectado por la emergencia. Sus usuarios tienen
    el rol `operador_municipal` y registran emergencias.
  - ong: organización no gubernamental o de rescate. Sus usuarios tienen
    el rol `representante_ong` y presentan ofertas de ayuda.
  - centro_coordinador_regional: centro coordinador regional. Sus usuarios tienen
    el rol `coordinador_regional` y gestionan emergencias.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensiones import db

if TYPE_CHECKING:
    from app.modulos.usuarios_roles.modelos import Usuario


class TipoOrganizacion(enum.Enum):
    """Clasificación del organismo en el sistema."""

    municipio = "municipio"
    ong = "ong"
    centro_coordinador_regional = "centro_coordinador_regional"


class Organizacion(db.Model):
    """Entidad Municipio u ONG colaboradora."""

    __tablename__ = "organizacion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    nombre: Mapped[str] = mapped_column(
        String(200),
        unique=True,
        nullable=False,
        index=True,
        comment="Nombre oficial del municipio u ONG.",
    )
    tipo: Mapped[TipoOrganizacion] = mapped_column(
        Enum(TipoOrganizacion, name="tipo_organizacion_enum"),
        nullable=False,
        comment="Indica si es un municipio o una ONG de ayuda/rescate.",
    )
    identificador_nacional: Mapped[str | None] = mapped_column(
        String(50),
        unique=True,
        nullable=True,
        comment="CUIT / RUC u otro identificador fiscal.",
    )
    contacto_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    contacto_telefono: Mapped[str | None] = mapped_column(String(50), nullable=True)
    direccion: Mapped[str | None] = mapped_column(String(255), nullable=True)

    activo: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Indica si el organismo está habilitado para operar.",
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # --- relaciones -----------------------------------------------------------
    usuarios: Mapped[list[Usuario]] = relationship(
        "Usuario",
        back_populates="organizacion",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Organizacion id={self.id} nombre={self.nombre!r} tipo={self.tipo.value}>"
