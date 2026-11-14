"""Modelos del módulo de emergencias de RescueSync.

Implementa el eslabón 1 y 2 del enunciado del TP:
1. Registro de Emergencia: Un municipio afectado por un desastre registra una
   emergencia detallando nivel de gravedad, zona afectada y descripción.
2. Generación de Lotes: El Centro Coordinador Regional revisa la emergencia y
   la desglosa en "Lotes" compuestos por "Items" cuantificados (LoteItem).
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
from sqlalchemy.sql.sqltypes import Boolean

from app.extensiones import db

if TYPE_CHECKING:
    from app.modulos.convocatorias.modelos import Convocatoria
    from app.modulos.organizaciones.modelos import Organizacion
    from app.modulos.usuarios_roles.modelos import Usuario


class NivelGravedad(enum.Enum):
    """Nivel de severidad de la emergencia."""

    baja = "baja"
    media = "media"
    alta = "alta"
    critica = "critica"


class EstadoEmergencia(enum.Enum):
    """Ciclo de vida de una emergencia."""

    registrada = "registrada"
    en_evaluacion = "en_evaluacion"
    activa = "activa"
    finalizada = "finalizada"
    cancelada = "cancelada"


class TipoEmergencia(enum.Enum):
    incendio = "incendio"
    inundacion = "inundacion"
    terremoto = "terremoto"
    epidemia = "epidemia"
    otros = "otros"


class TipoNecesidad(enum.Enum):
    """Categorías estándar para los recursos e ítems de ayuda."""

    personal_medico = "personal_medico"
    rescate = "rescate"
    alimentos = "alimentos"
    agua = "agua"
    abrigo = "abrigo"
    medicamentos = "medicamentos"
    maquinaria = "maquinaria"
    otro = "otro"


class EstadoLote(enum.Enum):
    """Estado del lote de necesidades dentro de la gestión de la convocatoria."""

    pendiente = "pendiente"
    en_convocatoria = "en_convocatoria"
    adjudicado_parcial = "adjudicado_parcial"
    adjudicado_total = "adjudicado_total"
    cancelado = "cancelado"


class Emergencia(db.Model):
    """Emergencia registrada por un municipio afectado."""

    __tablename__ = "emergencia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    titulo: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Título o denominación breve de la emergencia.",
    )
    descripcion: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Descripción detallada de la situación inicial y daños.",
    )
    nivel_gravedad: Mapped[NivelGravedad] = mapped_column(
        Enum(NivelGravedad, name="nivel_gravedad_enum"),
        nullable=False,
    )
    zona_afectada: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Barrio, localidad o coordenadas de la zona afectada.",
    )
    estado: Mapped[EstadoEmergencia] = mapped_column(
        Enum(EstadoEmergencia, name="estado_emergencia_enum"),
        default=EstadoEmergencia.registrada,
        nullable=False,
    )
    tipo_emergencia: Mapped[TipoEmergencia] = mapped_column(
        Enum(TipoEmergencia, name="tipo_emergencia_enum"),
        nullable=False,
        default=TipoEmergencia.otros,
    )

    # ID de instancia de proceso en Bonita BPM asociado a esta emergencia.
    bonita_case_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # Municipio que originó la alerta
    municipio_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizacion.id"),
        nullable=False,
        index=True,
    )

    # Usuario operador municipal que cargó el formulario
    usuario_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("usuarios.id"),
        nullable=False,
    )

    # Fecha de registro. Indexada porque el panel de auditoria filtra por periodo sobre ella.
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # --- relaciones -----------------------------------------------------------
    municipio: Mapped[Organizacion] = relationship("Organizacion", lazy="select")
    usuario: Mapped[Usuario] = relationship("Usuario", lazy="select")
    lotes: Mapped[list[LoteNecesidad]] = relationship(
        "LoteNecesidad",
        back_populates="emergencia",
        lazy="select",
    )
    convocatorias: Mapped[list[Convocatoria]] = relationship(
        "Convocatoria",
        back_populates="emergencia",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Emergencia id={self.id} titulo={self.titulo!r} estado={self.estado.value}>"


class Item(db.Model):
    """Catálogo maestro de recursos, suministros y personal de auxilio."""

    __tablename__ = "item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo_recurso: Mapped[str] = mapped_column(
        String(200),
        unique=True,
        nullable=False,
        index=True,
    )

    nombre: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        nullable=False,
        index=True,
        comment="Nombre del recurso (ej: 'Paramédicos', 'Raciones de alimento', 'Agua potable').",
    )
    categoria: Mapped[TipoNecesidad] = mapped_column(
        Enum(TipoNecesidad, name="tipo_necesidad_enum"),
        nullable=False,
    )
    unidad_medida: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Unidad de medida estándar: 'personas', 'raciones', 'litros', 'kg', 'unidades'.",
    )
    descripcion: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Especificaciones o requerimientos técnicos del ítem.",
    )

    consumible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # --- relaciones -----------------------------------------------------------
    lote_items: Mapped[list[LoteItem]] = relationship(
        "LoteItem",
        back_populates="item",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Item id={self.id} nombre={self.nombre!r} unidad={self.unidad_medida!r}>"


class LoteNecesidad(db.Model):
    """Lote de necesidades generado por el Centro Coordinador para una emergencia."""

    __tablename__ = "lote_necesidad"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    emergencia_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("emergencia.id"),
        nullable=False,
        index=True,
    )
    convocatoria_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("convocatoria.id"),
        nullable=True,
        index=True,
    )

    descripcion: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Detalle o nombre del lote (ej: 'Lote 1 - Víveres urgentes').",
    )
    estado: Mapped[EstadoLote] = mapped_column(
        Enum(EstadoLote, name="estado_lote_enum"),
        default=EstadoLote.pendiente,
        nullable=False,
    )

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # --- relaciones -----------------------------------------------------------
    emergencia: Mapped[Emergencia] = relationship("Emergencia", back_populates="lotes")
    convocatoria: Mapped[Convocatoria | None] = relationship("Convocatoria", back_populates="lotes")
    lote_items: Mapped[list[LoteItem]] = relationship(
        "LoteItem",
        back_populates="lote",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<LoteNecesidad id={self.id} emergencia_id={self.emergencia_id}"
            f" estado={self.estado.value}>"
        )


class LoteItem(db.Model):
    """Detalle de cantidad requerida de un ítem dentro de un lote específico."""

    __tablename__ = "lote_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    lote_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lote_necesidad.id"),
        nullable=False,
        index=True,
    )
    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("item.id"),
        nullable=False,
        index=True,
    )

    cantidad_solicitada: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Cantidad requerida del ítem en este lote.",
    )
    observaciones: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Aclaraciones específicas (ej: 'aptas para celíacos', '4x4').",
    )

    # --- relaciones -----------------------------------------------------------
    lote: Mapped[LoteNecesidad] = relationship("LoteNecesidad", back_populates="lote_items")
    item: Mapped[Item] = relationship("Item", back_populates="lote_items")

    def __repr__(self) -> str:
        return (
            f"<LoteItem id={self.id} lote_id={self.lote_id} "
            f"item_id={self.item_id} cant={self.cantidad_solicitada}>"
        )
