"""Formularios de validacion de entrada del modulo usuarios_roles.

Aca vive la validacion de forma: campo obligatorio, longitud, formato de email. La de negocio
-email ya usado, rol incompatible con la organizacion, contrasena actual incorrecta- vive en
`servicios.py`, porque tambien la necesitan el seeder y los comandos de consola, donde no hay
formulario ni solicitud HTTP.

La politica de contrasena se valida dos veces a proposito: aca para poder mostrar junto al
campo exactamente que le falta, y en el servicio para que ninguna via de alta se la saltee.
"""

from __future__ import annotations

from typing import Any

from flask import current_app
from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, PasswordField, SelectField, StringField
from wtforms.validators import EqualTo, InputRequired, Length, Optional, Regexp, ValidationError

from app.core.permisos import ETIQUETA_POR_ROL, NombreRol
from app.core.seguridad import (
    MENSAJE_EMAIL_INVALIDO,
    PATRON_DE_EMAIL,
    mensaje_de_politica,
    requisitos_incumplidos,
)


class PoliticaDeContrasena:
    """Validador WTForms de la politica de `app.core.seguridad`.

    Lee la longitud minima de la configuracion en cada validacion, asi el formulario y el
    servicio exigen siempre lo mismo.
    """

    def __call__(self, formulario: Any, campo: Any) -> None:
        minima = int(current_app.config["CONTRASENA_LONGITUD_MINIMA"])
        incumplidos = requisitos_incumplidos(campo.data or "", minima)
        if incumplidos:
            raise ValidationError(mensaje_de_politica(incumplidos, minima))


# (valor, texto): el valor es el que viaja y se valida; el texto es el que ve la persona.
OPCIONES_DE_ROL = [(rol.value, ETIQUETA_POR_ROL[rol]) for rol in NombreRol]


class FormularioIngreso(FlaskForm):
    """Inicio de sesion.

    La contrasena no lleva validador de longitud: exigirla acá filtraria cuál es la política
    a quien todavía no se autenticó, y una contraseña vieja más corta no debe quedar sin poder
    entrar a cambiarla.
    """

    email = StringField(
        "Email",
        validators=[InputRequired("El email es obligatorio."), Length(max=254)],
    )
    contrasena = PasswordField(
        "Contraseña",
        validators=[InputRequired("La contraseña es obligatoria.")],
    )


class FormularioAltaDeUsuario(FlaskForm):
    """Alta de una cuenta por parte del administrador."""

    email = StringField(
        "Email",
        validators=[
            InputRequired("El email es obligatorio."),
            Regexp(PATRON_DE_EMAIL, message=MENSAJE_EMAIL_INVALIDO),
            Length(max=254),
        ],
    )
    nombre_completo = StringField(
        "Nombre completo",
        validators=[InputRequired("El nombre completo es obligatorio."), Length(max=255)],
    )
    contrasena = PasswordField(
        "Contraseña inicial",
        validators=[
            InputRequired("La contraseña inicial es obligatoria."),
            PoliticaDeContrasena(),
        ],
    )
    rol = SelectField(
        "Rol",
        choices=OPCIONES_DE_ROL,
        validators=[InputRequired("El rol es obligatorio.")],
    )
    organizacion_id = IntegerField("Organización", validators=[Optional()])


class FormularioEdicionDeUsuario(FlaskForm):
    """Edicion de una cuenta. El email no se edita: es la clave natural del login."""

    nombre_completo = StringField(
        "Nombre completo",
        validators=[InputRequired("El nombre completo es obligatorio."), Length(max=255)],
    )
    rol = SelectField(
        "Rol",
        choices=OPCIONES_DE_ROL,
        validators=[InputRequired("El rol es obligatorio.")],
    )
    organizacion_id = IntegerField("Organización", validators=[Optional()])


class FormularioEstadoDeUsuario(FlaskForm):
    """Activacion o desactivacion de una cuenta."""

    activo = BooleanField("Activa")


class FormularioRestablecerContrasena(FlaskForm):
    """Contrasena nueva asignada por el administrador."""

    contrasena = PasswordField(
        "Contraseña nueva",
        validators=[
            InputRequired("La contraseña nueva es obligatoria."),
            PoliticaDeContrasena(),
        ],
    )


class FormularioCambioDeContrasena(FlaskForm):
    """Cambio de contrasena por parte del propio usuario."""

    contrasena_actual = PasswordField(
        "Contraseña actual",
        validators=[InputRequired("La contraseña actual es obligatoria.")],
    )
    contrasena_nueva = PasswordField(
        "Contraseña nueva",
        validators=[
            InputRequired("La contraseña nueva es obligatoria."),
            PoliticaDeContrasena(),
        ],
    )
    contrasena_nueva_repetida = PasswordField(
        "Repetir contraseña nueva",
        validators=[
            InputRequired("Repetí la contraseña nueva."),
            EqualTo("contrasena_nueva", "Las contraseñas no coinciden."),
        ],
    )
