"""Modelos de usuarios, roles y permisos de RescueSync.

Implementa el Control de Accesos Basado en Roles (RBAC) con tablas relacionales:
  - `usuarios`: cuentas de usuario del sistema (operadores, coordinadores, ONGs, auditores).
  - `roles`: perfiles del sistema (operador_municipal, coordinador_regional,
    representante_ong, auditor, admin, etc).
  - `permisos`: operaciones atómicas permitidas (ej: emergencia:crear, oferta:postular, etc.).
  - `usuario_rol`: tabla asociativa M:N entre usuarios y roles.
  - `rol_permiso`: tabla asociativa M:N entre roles y permisos.

Relación con Organización
--------------------------
Un Usuario puede pertenecer a una Organización (Municipio u ONG).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from flask_login import UserMixin
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensiones import db

if TYPE_CHECKING:
    from app.modulos.organizaciones.modelos import Organizacion


# --- Tablas intermedias M:N ---------------------------------------------------

# Tabla que no estaba en el diagrama pero considero que no está mal que esté
# para no limitar a que cada usuario tenga solo un rol.
usuario_rol = Table(
    "usuario_rol",
    db.metadata,
    Column("usuario_id", Integer, ForeignKey("usuarios.id"), primary_key=True),
    Column("rol_id", Integer, ForeignKey("roles.id"), primary_key=True),
)

rol_permiso = Table(
    "rol_permiso",
    db.metadata,
    Column("rol_id", Integer, ForeignKey("roles.id"), primary_key=True),
    Column("permiso_id", Integer, ForeignKey("permisos.id"), primary_key=True),
)


# --- Modelos RBAC -------------------------------------------------------------


class Permiso(db.Model):
    """Permiso o acción granular del sistema."""

    __tablename__ = "permisos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    nombre: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Código identificador del permiso, ej: 'emergencias:crear', 'ofertas:editar'.",
    )
    descripcion: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Descripción legible para auditoría.",
    )

    # --- relaciones -----------------------------------------------------------
    roles: Mapped[list[Rol]] = relationship(
        "Rol",
        secondary=rol_permiso,
        back_populates="permisos",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Permiso id={self.id} nombre={self.nombre!r}>"


class Rol(db.Model):
    """Perfil de acceso del sistema que agrupa permisos."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    nombre: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Nombre único del rol: operador_municipal, coordinador_regional, etc.",
    )
    descripcion: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Descripción de las responsabilidades del rol.",
    )

    # --- relaciones -----------------------------------------------------------
    permisos: Mapped[list[Permiso]] = relationship(
        "Permiso",
        secondary=rol_permiso,
        back_populates="roles",
        lazy="selectin",
    )
    usuarios: Mapped[list[Usuario]] = relationship(
        "Usuario",
        secondary=usuario_rol,
        back_populates="roles",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Rol id={self.id} nombre={self.nombre!r}>"


class Usuario(UserMixin, db.Model):
    """Cuenta de acceso al sistema."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    email: Mapped[str] = mapped_column(
        String(254),
        unique=True,
        nullable=False,
        index=True,
        comment="Clave natural. Se usa como identificador en el login.",
    )
    hash_contrasena: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        comment="Hash scrypt generado por app.core.seguridad.hashear_contrasena().",
    )
    nombre_completo: Mapped[str] = mapped_column(String(255), nullable=False)

    # NULL para coordinador_regional y auditor; obligatorio para operador_municipal y ONG.
    organizacion_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("organizacion.id"),
        nullable=True,
    )

    activo: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="False deshabilita el login sin borrar la cuenta.",
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # --- relaciones -----------------------------------------------------------

    # Organización (Municipio u ONG) a la que pertenece el usuario.
    organizacion: Mapped[Organizacion | None] = relationship(
        "Organizacion",
        back_populates="usuarios",
        lazy="select",
    )

    # Roles asignados al usuario (M:N)
    roles: Mapped[list[Rol]] = relationship(
        "Rol",
        secondary=usuario_rol,
        back_populates="usuarios",
        lazy="selectin",
    )

    # --- propiedades Flask-Login ----------------------------------------------

    @property
    def is_active(self) -> bool:  # type: ignore[override]
        """Flask-Login llama esto para saber si la cuenta puede iniciar sesión."""
        return self.activo

    # --- helpers de permisos y roles ------------------------------------------

    @property
    def rol_principal(self) -> str | None:
        """Devuelve el nombre del primer rol asignado, si existe."""
        return self.roles[0].nombre if self.roles else None

    def tiene_rol(self, nombre_rol: str) -> bool:
        """Verifica si el usuario tiene asignado un rol específico."""
        return any(r.nombre == nombre_rol for r in self.roles)

    def tiene_permiso(self, codigo_permiso: str) -> bool:
        """Verifica si alguno de los roles del usuario posee el permiso indicado."""
        for rol in self.roles:
            if any(p.nombre == codigo_permiso for p in rol.permisos):
                return True
        return False

    def es_operador_municipal(self) -> bool:
        return self.tiene_rol("operador_municipal")

    def es_coordinador_regional(self) -> bool:
        return self.tiene_rol("coordinador_regional")

    def es_representante_ong(self) -> bool:
        return self.tiene_rol("representante_ong")

    def es_auditor(self) -> bool:
        return self.tiene_rol("auditor")

    def __repr__(self) -> str:
        roles_str = ",".join(r.nombre for r in self.roles)
        return f"<Usuario id={self.id} email={self.email!r} roles=[{roles_str}]>"
