"""Formularios de validacion de entrada del modulo organizaciones.

La validacion de forma (campo obligatorio, longitud, formato de email) vive aca; la de negocio
(nombre ya usado, identificador repetido) vive en `servicios.py`. La separacion importa: los
servicios los llama tambien el seeder y la CLI, donde no hay solicitud HTTP ni formulario.
"""

from __future__ import annotations

from collections.abc import Iterable

from flask_wtf import FlaskForm
from sqlalchemy import select
from wtforms import BooleanField, IntegerField, SelectField, StringField
from wtforms.validators import InputRequired, Length, NumberRange, Optional, Regexp

from app.core.acceso.permisos import ETIQUETA_POR_TIPO_DE_ORGANIZACION
from app.core.acceso.seguridad import MENSAJE_EMAIL_INVALIDO, PATRON_DE_EMAIL
from app.extensiones import db
from app.modulos.emergencias.modelos import Item
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


class FormularioInventarioItem(FlaskForm):
    """Alta y edicion de la cantidad de un item dentro de un inventario."""

    item_id = SelectField(
        "Item",
        coerce=int,
        validators=[InputRequired("El item es obligatorio.")],
    )
    cantidad_disponible = IntegerField(
        "Cantidad disponible",
        validators=[
            InputRequired("La cantidad es obligatoria."),
            NumberRange(
                min=0,
                max=9999999999,
                message="La cantidad debe estar entre 0 y 9.999.999.999.",
            ),
        ],
    )

    def __init__(
        self,
        *args,
        items: Iterable[Item] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        if items is None:
            items = db.session.scalars(select(Item).order_by(Item.nombre)).all()
        self.item_id.choices = [(item.id, item.nombre) for item in items]

