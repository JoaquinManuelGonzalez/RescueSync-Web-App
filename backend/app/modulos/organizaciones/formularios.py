"""Formularios de validacion de entrada del modulo organizaciones.

La validacion de forma (campo obligatorio, longitud, formato de email) vive aca; la de negocio
(nombre ya usado, identificador repetido) vive en `servicios.py`. La separacion importa: los
servicios los llama tambien el seeder y la CLI, donde no hay solicitud HTTP ni formulario.
"""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, SelectField, StringField
from wtforms.validators import InputRequired, Length, Optional, Regexp

from app.core.permisos import ETIQUETA_POR_TIPO_DE_ORGANIZACION
from app.core.seguridad import MENSAJE_EMAIL_INVALIDO, PATRON_DE_EMAIL
from app.modulos.organizaciones.modelos import TipoOrganizacion

# (valor, texto): el valor es el que viaja y se valida; el texto es el que ve la persona.
OPCIONES_DE_TIPO = [
    (tipo.value, ETIQUETA_POR_TIPO_DE_ORGANIZACION.get(tipo.value, tipo.value))
    for tipo in TipoOrganizacion
]


class FormularioOrganizacion(FlaskForm):
    """Alta y edicion de un municipio, una ONG o el centro coordinador."""

    nombre = StringField(
        "Nombre",
        validators=[InputRequired("El nombre es obligatorio."), Length(max=200)],
    )
    tipo = SelectField(
        "Tipo",
        choices=OPCIONES_DE_TIPO,
        validators=[InputRequired("El tipo es obligatorio.")],
    )
    identificador_nacional = StringField(
        "Identificador nacional",
        validators=[Optional(), Length(max=50)],
    )
    contacto_email = StringField(
        "Email de contacto",
        validators=[
            Optional(),
            Regexp(PATRON_DE_EMAIL, message=MENSAJE_EMAIL_INVALIDO),
            Length(max=254),
        ],
    )
    contacto_telefono = StringField(
        "Teléfono de contacto",
        validators=[Optional(), Length(max=50)],
    )
    direccion = StringField("Dirección", validators=[Optional(), Length(max=255)])


class FormularioEstado(FlaskForm):
    """Activacion o desactivacion de una organizacion."""

    activo = BooleanField("Activa")
