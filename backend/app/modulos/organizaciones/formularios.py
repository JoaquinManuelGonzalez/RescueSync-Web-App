"""Formularios de validacion de entrada del modulo organizaciones.

La validacion de forma (campo obligatorio, longitud, formato de email) vive aca; la de negocio
(nombre ya usado, identificador repetido) vive en `servicios.py`. La separacion importa: los
servicios los llama tambien el seeder y la CLI, donde no hay solicitud HTTP ni formulario.
"""

from __future__ import annotations

from collections.abc import Iterable

from flask_wtf import FlaskForm
from sqlalchemy import select
from wtforms import (
    BooleanField,
    FieldList,
    Form,
    FormField,
    IntegerField,
    SelectField,
    StringField,
)
from wtforms.validators import InputRequired, Length, NumberRange, Optional, Regexp

from app.core.acceso.permisos import ETIQUETA_POR_TIPO_DE_ORGANIZACION
from app.core.acceso.seguridad import MENSAJE_EMAIL_INVALIDO, PATRON_DE_EMAIL
from app.core.identificadores import exigir_id
from app.extensiones import db
from app.modulos.emergencias.modelos import Item
from app.modulos.organizaciones.geografia import OPCIONES_DE_PROVINCIA
from app.modulos.organizaciones.modelos import TipoOrganizacion

# (valor, texto): el valor es el que viaja y se valida; el texto es el que ve la persona.
OPCIONES_DE_TIPO = [
    (tipo.value, ETIQUETA_POR_TIPO_DE_ORGANIZACION.get(tipo.value, tipo.value))
    for tipo in TipoOrganizacion
]


# Tope de filas de cobertura por envio: mas que suficiente para cualquier organizacion real y
# evita que un formulario armado a mano haga crecer la lista sin limite.
MAXIMO_DE_ZONAS = 50


class FormularioZona(Form):
    """Una fila de la zona de cobertura.

    Es un `Form` de WTForms y no un `FlaskForm`: va anidado en otro formulario, que ya trae su
    propio token CSRF. Las filas no llevan validadores: provincia valida y longitud de la
    localidad las controla `servicios.normalizar_zonas()`, que es la misma regla para el
    formulario, el JSON y el seeder, y devuelve todos los errores de cobertura juntos bajo el
    campo `zonas` para mostrarlos en un unico lugar.
    """

    provincia = SelectField(
        "Provincia",
        choices=[("", "Elegí una provincia"), *OPCIONES_DE_PROVINCIA],
        validate_choice=False,
    )
    localidad = StringField("Localidades o partidos")


class FormularioDatosPropios(FlaskForm):
    """Lo que un miembro puede actualizar de su propia organizacion: contacto y cobertura."""

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
    cobertura_nacional = BooleanField("Opera en todo el país")
    zonas = FieldList(
        FormField(FormularioZona),
        "Zona de cobertura",
        min_entries=1,
        max_entries=MAXIMO_DE_ZONAS,
    )

    def fila_de_zona_vacia(self) -> FormularioZona:
        """Fila modelo para el <template> que clona `zonas_de_cobertura.js` al agregar una zona.

        El marcador `__indice__` lo reemplaza el script por un numero que no este en uso; WTForms
        acepta indices salteados, asi que quitar una fila no obliga a renumerar las demas.
        """
        return FormularioZona(prefix=f"{self.zonas.name}-__indice__-")


class FormularioOrganizacion(FormularioDatosPropios):
    """Alta y edicion de un municipio, una ONG o el centro coordinador, por el administrador.

    Hereda contacto y cobertura de `FormularioDatosPropios`. No lleva el estado de verificacion:
    ese dato solo lo escribe la integracion con el Sistema Nacional.
    """

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


class FormularioEstado(FlaskForm):
    """Activacion o desactivacion de una organizacion."""

    activo = BooleanField("Activa")


class FormularioInventarioItem(FlaskForm):
    """Alta y edicion de la cantidad de un item dentro de un inventario."""

    item_id = SelectField(
        "Item",
        coerce=exigir_id,
        validators=[InputRequired("El item es obligatorio.")],
    )
    cantidad_disponible = IntegerField(
        "Cantidad disponible",
        validators=[
            InputRequired("La cantidad es obligatoria."),
            NumberRange(
                min=1,
                max=9999999999,
                message="La cantidad debe estar entre 1 y 9.999.999.999.",
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
