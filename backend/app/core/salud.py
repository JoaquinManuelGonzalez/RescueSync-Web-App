"""Endpoint de salud del contenedor.

Lo consumen el healthcheck de docker-compose.yml
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.errores import construir_envelope
from app.core.logging import registrar_evento
from app.extensiones import db

blueprint_salud = Blueprint("salud", __name__)


@blueprint_salud.get("/health")
def consultar_salud():
    """Responde 200 si la aplicacion y la base de datos estan operativas."""
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        db.session.rollback()
        registrar_evento(
            logging.ERROR,
            "salud_degradada",
            type(error).__name__,
            componente="base_de_datos",
        )

        cuerpo = {
            "status": "error",
            "db": "error",
            **construir_envelope(
                "SERVICIO_EXTERNO_NO_DISPONIBLE",
                "La base de datos no responde en este momento.",
                {"componente": "base_de_datos"},
            ),
        }
        return jsonify(cuerpo), 503

    return jsonify({"status": "ok", "db": "ok"}), 200
