"""Pagina de inicio provisional del esqueleto.

Es una pagina de verificacion

Cuando exista el modulo usuarios_roles, la ruta "/" pasa a ser el login o el panel segun la
sesion, y este blueprint se elimina.
"""

from __future__ import annotations

from flask import Blueprint, render_template

blueprint_inicio = Blueprint("inicio", __name__)


@blueprint_inicio.get("/")
def mostrar_inicio():
    """Renderiza la pagina provisional de verificacion."""
    return render_template("inicio.html")
