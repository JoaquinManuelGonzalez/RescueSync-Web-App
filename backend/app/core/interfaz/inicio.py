"""Entrada a la aplicacion y panel de inicio.

- `GET /` es publica: no muestra nada, solo manda a cada quien a donde corresponde (el panel
  con sesion, la pantalla de ingreso sin ella).
- `GET /inicio` es el panel: saludo, perfil y un acceso por cada pantalla que el usuario puede
  usar. Los accesos salen de `app.core.interfaz.navegacion`, no de una lista de roles.
"""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user

from app.core.acceso.autorizacion import requiere_autenticacion

blueprint_inicio = Blueprint("inicio", __name__)


@blueprint_inicio.get("/")
def raiz():
    """Publica a proposito: redirige al panel o al ingreso segun haya sesion."""
    if current_user.is_authenticated:
        return redirect(url_for("inicio.panel"))
    return redirect(url_for("sesion.formulario_de_ingreso"))


@blueprint_inicio.get("/inicio")
@requiere_autenticacion
def panel():
    """Panel de inicio del usuario en sesion."""
    return render_template("hub.html")
