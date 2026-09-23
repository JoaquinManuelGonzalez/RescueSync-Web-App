"""Menu de la interfaz, declarado por cada modulo y filtrado por permiso.

Es la hipotesis de beneficio de la epica de identidad aplicada a la interfaz: una pantalla
nueva no escribe logica de visibilidad, **declara su entrada** con el permiso que la protege:

    ENTRADA_DE_MENU = EntradaDeMenu(
        endpoint="emergencias.listar",
        titulo="Emergencias",
        permiso=EMERGENCIAS_LISTAR,
        descripcion="Registro y seguimiento de emergencias",
        icono="carpeta",
    )

y `registrar_modulos()` la registra junto a su blueprint. A partir de ahi aparece como tarjeta
en el panel de inicio (`hub.html`) y como enlace en el navbar de quien tenga el permiso, y de
nadie mas.

Es solo presentacion. La ruta sigue protegida por su `@requiere_permiso`: una entrada que se
muestra de mas no habilita nada, y una que falta no protege nada.
"""

from __future__ import annotations

from dataclasses import dataclass

from flask import Flask, current_app

from app.core.acceso.autorizacion import puede

CLAVE_DE_EXTENSION = "rescuesync.menu"


@dataclass(frozen=True)
class EntradaDeMenu:
    """Una seccion del sistema: tarjeta del panel de inicio y enlace del navbar.

    `icono` es un nombre del diccionario de iconos de `frontend/plantillas/hub.html`.
    `orden` define la posicion: menor va primero.
    """

    endpoint: str
    titulo: str
    permiso: str
    descripcion: str = ""
    icono: str = "carpeta"
    orden: int = 100

    @property
    def blueprint(self) -> str:
        """Blueprint de la pantalla, para marcar la seccion activa en el navbar."""
        return self.endpoint.partition(".")[0]


def registrar_entrada(app: Flask, entrada: EntradaDeMenu) -> None:
    """Suma una entrada al menu de la aplicacion.

    Se guarda en `app.extensions` y no en una lista global para que cada aplicacion (y cada
    test que construye la suya) tenga su propio menu, sin entradas duplicadas.
    """
    app.extensions.setdefault(CLAVE_DE_EXTENSION, []).append(entrada)


def entradas_de_menu() -> list[EntradaDeMenu]:
    """Las entradas que el usuario en sesion puede usar, en orden. Vacia sin sesion."""
    registradas: list[EntradaDeMenu] = current_app.extensions.get(CLAVE_DE_EXTENSION, [])
    visibles = [entrada for entrada in registradas if puede(entrada.permiso)]
    return sorted(visibles, key=lambda entrada: (entrada.orden, entrada.titulo))


def registrar_navegacion(app: Flask) -> None:
    """Deja `entradas_de_menu()` disponible en cualquier plantilla Jinja."""
    app.jinja_env.globals["entradas_de_menu"] = entradas_de_menu
