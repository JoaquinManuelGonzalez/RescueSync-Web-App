"""Pantallas y acciones de notificaciones."""

from __future__ import annotations

import uuid

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user

from app.core.acceso.autorizacion import requiere_autenticacion
from app.modulos.notificaciones import servicios

blueprint_notificaciones = Blueprint("notificaciones", __name__)


@blueprint_notificaciones.get("")
@requiere_autenticacion
def listar():
    return render_template(
        "notificaciones.html",
        notificaciones=servicios.listar_para_usuario(current_user.id),
    )


@blueprint_notificaciones.get("/<uuid:notificacion_id>/abrir")
@requiere_autenticacion
def abrir(notificacion_id: uuid.UUID):
    notificacion = servicios.marcar_como_leida(notificacion_id, current_user.id)
    return redirect(notificacion.enlace or url_for("notificaciones.listar"))
