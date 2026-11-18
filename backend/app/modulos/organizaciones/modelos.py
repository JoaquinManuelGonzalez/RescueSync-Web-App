"""Modelos de municipios y organizaciones de RescueSync.

Una organizacion representa a una entidad externa que participa en el sistema.
Existen tres tipos principales según el enunciado:
  - municipio: municipio afectado por la emergencia. Sus usuarios tienen
    el rol `operador_municipal` y registran emergencias.
  - ong: organización no gubernamental o de rescate. Sus usuarios tienen
    el rol `representante_ong` y presentan ofertas de ayuda.
  - centro_coordinador_regional: centro coordinador regional. Sus usuarios tienen
    el rol `coordinador_regional` y gestionan emergencias.

Cada organizacion declara su zona de cobertura (`ZonaDeCobertura`), o marca que opera en todo el
pais (`cobertura_nacional`, que reemplaza a las zonas). Tambien lleva el estado de su verificacion
contra el Sistema Nacional (`EstadoVerificacion`): toda organizacion que se carga en RescueSync ya
fue verificada por el Sistema Nacional, asi que nace `verificada`.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.identificadores import nuevo_id
from app.extensiones import db

if TYPE_CHECKING:
    from app.modulos.emergencias.modelos import Item
    from app.modulos.usuarios_roles.modelos import Usuario


class TipoOrganizacion(enum.Enum):
    """Clasificación del organismo en el sistema."""

    municipio = "municipio"
    ong = "ong"
    centro_coordinador_regional = "centro_coordinador_regional"


class EstadoVerificacion(enum.Enum):
    """Resultado de validar la organizacion contra el Sistema Nacional.

    Nace `verificada`: las organizaciones se cargan en RescueSync despues de que el Sistema
    Nacional las verifico. Ningun formulario lo cambia; solo la integracion con la API Nacional
    podria registrar otro resultado (ver `servicios.registrar_resultado_de_verificacion()`).
    """

    sin_verificar = "sin_verificar"
    verificada = "verificada"
    rechazada = "rechazada"


class Organizacion(db.Model):
    """Entidad Municipio u ONG colaboradora."""

    __tablename__ = "organizacion"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=nuevo_id)

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
    cobertura_nacional: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
        comment="True si opera en todo el país: reemplaza a las zonas de cobertura.",
    )
    estado_verificacion: Mapped[EstadoVerificacion] = mapped_column(
        Enum(EstadoVerificacion, name="estado_verificacion_enum"),
        default=EstadoVerificacion.verificada,
        server_default=EstadoVerificacion.verificada.value,
        nullable=False,
        comment="Resultado de la validación contra el Sistema Nacional.",
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
    zonas_de_cobertura: Mapped[list[ZonaDeCobertura]] = relationship(
        "ZonaDeCobertura",
        back_populates="organizacion",
        cascade="all, delete-orphan",
        order_by="(ZonaDeCobertura.provincia, ZonaDeCobertura.localidad)",
        lazy="selectin",
    )
    usuarios: Mapped[list[Usuario]] = relationship(
        "Usuario",
        back_populates="organizacion",
        lazy="select",
    )
    inventario: Mapped[Inventario | None] = relationship(
        "Inventario",
        back_populates="organizacion",
        uselist=False,
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Organizacion id={self.id} nombre={self.nombre!r} tipo={self.tipo.value}>"


# Mismo criterio que el email de las cuentas (ver usuarios_roles/modelos.py): el UNIQUE de la
# columna distingue mayusculas y dejaria convivir "Cruz Solidaria" y "cruz solidaria". Se declara
# fuera de la clase para que `func.lower` reciba la columna ya mapeada y no la cadena literal.
Index("uq_organizacion_nombre_normalizado", func.lower(Organizacion.nombre), unique=True)


class ZonaDeCobertura(db.Model):
    """Una zona en la que la organizacion puede operar.

    La provincia sale de la lista cerrada de `geografia.PROVINCIAS`; la localidad es opcional y,
    si falta, la zona es la provincia completa. La normalizacion (duplicados, localidades que ya
    cubre la provincia completa) vive en `servicios.py`.
    """

    __tablename__ = "organizacion_zona_cobertura"
    __table_args__ = (
        UniqueConstraint(
            "organizacion_id",
            "provincia",
            "localidad",
            name="uq_organizacion_zona_cobertura",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizacion.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provincia: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        index=True,
        comment="Nombre oficial de la provincia (lista cerrada de geografia.PROVINCIAS).",
    )
    localidad: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        comment="Partido o localidad. NULL significa toda la provincia.",
    )

    organizacion: Mapped[Organizacion] = relationship(
        "Organizacion",
        back_populates="zonas_de_cobertura",
    )

    def __repr__(self) -> str:
        return (
            f"<ZonaDeCobertura organizacion_id={self.organizacion_id}"
            f" provincia={self.provincia!r} localidad={self.localidad!r}>"
        )


class Inventario(db.Model):
    """Stock de recursos disponibles de una organización.

    La relación con Organizacion es 1:1: `organizacion_id` es `unique`, de modo que cada
    organización tiene un único inventario. El desglose por recurso vive en InventarioItem.
    """

    __tablename__ = "inventario"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizacion.id"),
        nullable=False,
        unique=True,  # 1:1 — cada organizacion tiene un solo inventario
    )
    nombre: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        comment="Nombre descriptivo del inventario (ej: 'Depósito central', 'Almacén norte').",
    )
    descripcion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # --- relaciones -----------------------------------------------------------
    organizacion: Mapped[Organizacion] = relationship(
        "Organizacion",
        back_populates="inventario",
        lazy="select",
    )
    items: Mapped[list[InventarioItem]] = relationship(
        "InventarioItem",
        back_populates="inventario",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<Inventario id={self.id} organizacion_id={self.organizacion_id}"
            f" nombre={self.nombre!r}>"
        )


class InventarioItem(db.Model):
    """Cantidad disponible de un Item en un Inventario.

    Tabla asociativa entre Inventario e Item con la cantidad actual en stock.
    """

    __tablename__ = "inventario_item"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=nuevo_id)
    inventario_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("inventario.id"),
        nullable=False,
        index=True,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("item.id"),
        nullable=False,
        index=True,
    )
    cantidad_disponible: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Cantidad del item actualmente disponible en el inventario.",
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # --- relaciones -----------------------------------------------------------
    inventario: Mapped[Inventario] = relationship(
        "Inventario",
        back_populates="items",
        lazy="select",
    )
    item: Mapped[Item] = relationship(
        "Item",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<InventarioItem inventario_id={self.inventario_id}"
            f" item_id={self.item_id} cantidad={self.cantidad_disponible}>"
        )
