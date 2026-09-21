"""Modelos de usuarios, roles y permisos de RescueSync.

Implementa el Control de Accesos Basado en Roles (RBAC) con tablas relacionales:
  - `usuarios`: cuentas de usuario del sistema (operadores, coordinadores, ONGs, auditores).
  - `roles`: perfiles del sistema (operador_municipal, coordinador_regional,
    representante_ong, auditor, administrador).
  - `permisos`: operaciones atómicas permitidas (ej: emergencias:crear, ofertas:crear, etc.).
  - `usuario_rol`: tabla asociativa M:N entre usuarios y roles.
  - `rol_permiso`: tabla asociativa M:N entre roles y permisos.

Los nombres de rol y los códigos de permiso no se escriben acá: viven en `constantes.py`, que
es la fuente de verdad, y llegan a la base por `semillas.py`.

Relación con Organización
--------------------------
Un Usuario puede pertenecer a una Organización (Municipio, ONG o Centro Coordinador). Qué rol
exige qué tipo de organización lo decide `constantes.TIPO_DE_ORGANIZACION_POR_ROL` y lo hace
cumplir `servicios.py`: no es una restricción de base porque cruza tres tablas.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from flask_login import UserMixin
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensiones import db
from app.modulos.usuarios_roles.constantes import NombreRol

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
        comment="Clave natural, siempre normalizada a minúsculas. Identificador del login.",
    )
    hash_contrasena: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        comment="Hash scrypt generado por app.core.seguridad.hashear_contrasena().",
    )
    nombre_completo: Mapped[str] = mapped_column(String(255), nullable=False)

    # Obligatoria para operador_municipal, coordinador_regional y representante_ong; NULL para
    # auditor y administrador. La regla completa vive en constantes.TIPO_DE_ORGANIZACION_POR_ROL.
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

    # --- control de acceso ----------------------------------------------------

    debe_cambiar_contrasena: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
        comment=(
            "True obliga a cambiar la contraseña antes de operar. Las cuentas creadas por el "
            "administrador nacen así, para que la clave inicial no quede en uso."
        ),
    )
    intentos_fallidos: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
        comment="Intentos de ingreso fallidos consecutivos. Se resetea al ingresar bien.",
    )
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment=(
            "Momento hasta el cual la cuenta no puede iniciar sesión. NULL si no está bloqueada."
        ),
    )
    ultimo_acceso_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Último ingreso exitoso.",
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

    # Organización (Municipio, ONG o Centro Coordinador) a la que pertenece el usuario.
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

    def nombres_de_rol(self) -> frozenset[str]:
        """Nombres de todos los roles asignados."""
        return frozenset(rol.nombre for rol in self.roles)

    def permisos_efectivos(self) -> frozenset[str]:
        """Unión de los códigos de permiso de todos los roles del usuario.

        Es lo que consultan los decoradores de `app.core.autorizacion` y lo que la interfaz
        recibe para decidir qué mostrar. Se calcula sobre las relaciones ya cargadas: `roles`
        es `selectin` y `Rol.permisos` también, así que resolverlo cuesta dos consultas, no N.
        """
        return frozenset(permiso.nombre for rol in self.roles for permiso in rol.permisos)

    def tiene_rol(self, nombre_rol: str) -> bool:
        """Verifica si el usuario tiene asignado un rol específico."""
        return nombre_rol in self.nombres_de_rol()

    def tiene_permiso(self, codigo_permiso: str) -> bool:
        """Verifica si alguno de los roles del usuario posee el permiso indicado."""
        return codigo_permiso in self.permisos_efectivos()

    def esta_bloqueado(self) -> bool:
        """Indica si la cuenta está bloqueada por intentos fallidos en este momento."""
        if self.bloqueado_hasta is None:
            return False
        # Las fechas de PostgreSQL vienen con tzinfo; las de SQLite, en los tests, no.
        limite = self.bloqueado_hasta
        if limite.tzinfo is None:
            limite = limite.replace(tzinfo=UTC)
        return limite > datetime.now(UTC)

    def es_operador_municipal(self) -> bool:
        return self.tiene_rol(NombreRol.OPERADOR_MUNICIPAL)

    def es_coordinador_regional(self) -> bool:
        return self.tiene_rol(NombreRol.COORDINADOR_REGIONAL)

    def es_representante_ong(self) -> bool:
        return self.tiene_rol(NombreRol.REPRESENTANTE_ONG)

    def es_auditor(self) -> bool:
        return self.tiene_rol(NombreRol.AUDITOR)

    def es_administrador(self) -> bool:
        return self.tiene_rol(NombreRol.ADMINISTRADOR)

    def __repr__(self) -> str:
        roles_str = ",".join(r.nombre for r in self.roles)
        return f"<Usuario id={self.id} email={self.email!r} roles=[{roles_str}]>"


# El UNIQUE de la columna `email` no alcanza: distingue mayúsculas, así que dejaría entrar
# "Juan@x.com" y "juan@x.com" como dos cuentas distintas. `servicios.py` normaliza siempre a
# minúsculas y este índice funcional lo hace cumplir también para cualquier escritura que lo
# esquive (una semilla, una carga manual, un script). Se declara fuera de la clase porque dentro
# del cuerpo la columna todavía no está mapeada y `func.lower("email")` indexaría la cadena
# literal, no el campo.
Index("uq_usuarios_email_normalizado", func.lower(Usuario.email), unique=True)
