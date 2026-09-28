"""Entrada publica a la aplicacion y panel de inicio.

- `GET /` es publica: muestra la landing o manda al panel si ya hay una sesion.
- `GET /inicio` es el panel: saludo, perfil y un acceso por cada pantalla que el usuario puede
  usar. Los accesos salen de `app.core.interfaz.navegacion`, no de una lista de roles.
"""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user

from app.core.acceso.autorizacion import requiere_autenticacion
from app.extensiones import db
from app.modulos.emergencias.modelos import Emergencia
from app.modulos.ofertas.modelos import Oferta

blueprint_inicio = Blueprint("inicio", __name__)


@blueprint_inicio.get("/")
def raiz():
    """Publica a proposito: muestra la landing o el panel segun haya sesion."""
    if current_user.is_authenticated:
        return redirect(url_for("inicio.panel"))
    return render_template("landing.html")


@blueprint_inicio.get("/inicio")
@requiere_autenticacion
def panel():
    """Panel de inicio del usuario en sesion."""
    dashboard = None

    if current_user.tiene_rol("representante_ong"):
        items = db.session.scalars(
            db.select(Oferta)
            .where(
                Oferta.organizaciones_consorcio.any(
                    organizacion_id=current_user.organizacion_id,
                )
            )
            .order_by(Oferta.actualizado_en.desc(), Oferta.id.desc())
            .limit(5)
        ).all()
        dashboard = {
            "tipo": "ofertas",
            "titulo": "Estado de tus últimas ofertas",
            "descripcion": "Seguimiento de las propuestas de ayuda que enviaste.",
            "registros": items,
        }
    elif current_user.tiene_rol("operador_municipal"):
        items = db.session.scalars(
            db.select(Emergencia)
            .where(Emergencia.usuario_id == current_user.id)
            .order_by(Emergencia.actualizado_en.desc(), Emergencia.id.desc())
            .limit(1)
        ).all()
        dashboard = {
            "tipo": "emergencias_municipio",
            "titulo": "Estado de tu última emergencia",
            "descripcion": "Consultá cómo avanza la emergencia que registraste.",
            "registros": items,
        }
    elif current_user.tiene_rol("coordinador_regional"):
        items = db.session.scalars(
            db.select(Emergencia)
            .order_by(Emergencia.creado_en.desc(), Emergencia.id.desc())
            .limit(5)
        ).all()
        dashboard = {
            "tipo": "emergencias_regionales",
            "titulo": "Estado de las últimas emergencias",
            "descripcion": "Seguimiento de las emergencias cargadas en la red.",
            "registros": items,
        }

    return render_template("hub.html", dashboard=dashboard)
