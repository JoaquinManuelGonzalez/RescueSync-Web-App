"""Formularios de validación del módulo ejecución y cierre."""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, TextAreaField
from wtforms.validators import InputRequired, Length, Optional


class FormularioFinalizarTarea(FlaskForm):
    """Formulario para informar la finalización de una tarea en el terreno."""

    observaciones = TextAreaField(
        "Observaciones o informe de cierre",
        validators=[
            Optional(),
            Length(max=2000, message="Las observaciones no pueden superar los 2000 caracteres."),
        ],
    )
    confirmacion = BooleanField(
        "Confirmo que los recursos y tareas comprometidos fueron ejecutados y finalizados.",
        validators=[
            InputRequired(message="Debés tildar la confirmación para finalizar la tarea."),
        ],
    )
