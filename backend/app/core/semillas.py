"""Mecanismo de datos semilla.

Este modulo entrega el *mecanismo*, no los datos: el esquema de dominio lo define otra
persona del equipo. Cuando existan los modelos, cada modulo registra su propio seeder y el
comando `flask seed` los ejecuta en orden sin que haya que tocar nada mas.

Como agregar un seeder
----------------------
En el modulo correspondiente (por ejemplo `app/modulos/usuarios_roles/semillas.py`)::

    from app.core.acceso.seguridad import hashear_contrasena
    from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
    from app.modulos.usuarios_roles.modelos import Usuario

    @registrar("usuarios")
    def sembrar_usuarios() -> list[ResultadoSemilla]:
        resultado = ResultadoSemilla("usuarios")
        for email, rol in [("operador@rescuesync.test", "operador_municipal")]:
            _, fue_creado = obtener_o_crear(
                Usuario,
                claves={"email": email},
                valores={"rol": rol, "hash_contrasena": hashear_contrasena("cambiar123")},
            )
            resultado.contar(fue_creado, email=email)
        return [resultado]

Y en `app/core/semillas.py::importar_seeders()` se agrega el import del modulo nuevo.

Reglas
------
- Todo seeder es idempotente: se identifica cada registro por su clave natural con
  `obtener_o_crear()` y nunca por el id autonumerico.
- Ningun seeder hace `commit()`: el comando `flask seed` envuelve todo en una transaccion
  unica, de modo que si uno falla no queda media carga aplicada.
- Las contrasenas se generan siempre con `app.core.acceso.seguridad.hashear_contrasena()`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from app.extensiones import db


@dataclass
class ResultadoSemilla:
    """Cuenta lo que hizo un seeder sobre una entidad, para el resumen del comando."""

    entidad: str
    creados: int = 0
    existentes: int = 0
    # Emails de los usuarios creados o ya presentes, que el comando lista al terminar.
    emails: list[str] = field(default_factory=list)

    def contar(self, fue_creado: bool, email: str | None = None) -> None:
        if fue_creado:
            self.creados += 1
        else:
            self.existentes += 1
        if email:
            self.emails.append(email)


@dataclass(frozen=True)
class Seeder:
    nombre: str
    funcion: Callable[[], list[ResultadoSemilla]]


SEEDERS: list[Seeder] = []


def registrar(nombre: str) -> Callable[..., Any]:
    """Decorador que suma un seeder al registro que ejecuta `flask seed`."""

    def envoltorio(funcion: Callable[[], list[ResultadoSemilla]]):
        SEEDERS.append(Seeder(nombre=nombre, funcion=funcion))
        return funcion

    return envoltorio


def obtener_o_crear(
    modelo: type,
    *,
    claves: dict[str, Any],
    valores: dict[str, Any] | None = None,
) -> tuple[Any, bool]:
    """Busca una fila por su clave natural y la crea solo si no existe.

    Es lo que hace que volver a ejecutar `flask seed` no duplique nada.
    Devuelve la instancia y si hubo que crearla.
    """
    instancia = db.session.execute(select(modelo).filter_by(**claves)).scalar_one_or_none()
    if instancia is not None:
        return instancia, False

    instancia = modelo(**claves, **(valores or {}))
    db.session.add(instancia)
    # flush y no commit: hace visible el id para las relaciones sin cerrar la transaccion.
    db.session.flush()
    return instancia, True


def importar_seeders() -> None:
    """Importa los modulos que registran seeders.

    Los decoradores `@registrar` solo corren cuando su modulo se importa, asi que cada
    modulo de dominio que aporte datos semilla se agrega a esta lista.

    El orden de los imports es el orden de ejecucion: los items deben existir antes de que
    organizaciones cree sus inventarios, y usuarios se asocia a una organizacion ya cargada.
    """
    # from app.modulos.organizaciones import semillas as _organizaciones  # noqa: F401
    # from app.modulos.usuarios_roles import semillas as _usuarios_roles  # noqa: F401
    # from app.modulos.emergencias import semillas as _emergencias  # noqa: F401

    # Orden de sembrado:
    # items → organizaciones → inventarios → permisos → roles → usuarios → emergencias →
    # convocatorias → ofertas
    # El orden de estos imports es el orden de ejecución de los seeders.
    from app.modulos.emergencias import semillas_items as _items  # noqa: F401, I001
    from app.modulos.organizaciones import semillas as _organizaciones  # noqa: F401
    from app.modulos.usuarios_roles import semillas as _usuarios_roles  # noqa: F401
    from app.modulos.emergencias import semillas_emergencias as _emergencias  # noqa: F401, I001
    from app.modulos.convocatorias import semillas as _convocatorias  # noqa: F401, I001
    from app.modulos.ofertas import semillas as _ofertas  # noqa: F401, I001

    return
