"""Formularios del panel de auditoria.

Los filtros viajan por GET, en la query string: la URL de un periodo se puede compartir
y el boton "atras" del navegador funciona. Al ser una consulta de solo lectura, no lleva CSRF.
"""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import DateField, SelectField
from wtforms.validators import InputRequired, Optional, ValidationError

from app.core.interfaz.plantillas import etiqueta_gravedad
from app.modulos.emergencias.modelos import NivelGravedad
from app.modulos.indicadores.periodo import Periodo

MENSAJE_FECHA_INVALIDA = "Ingresá una fecha válida."
MENSAJE_PERIODO_INVERTIDO = "La fecha de inicio debe ser anterior a la de fin"


class CampoDeFecha(DateField):
    """`DateField` (`<input type="date">`, formato ISO) con el mensaje de error en castellano."""

    def process_formdata(self, valuelist):
        try:
            super().process_formdata(valuelist)
        except ValueError:
            raise ValueError(MENSAJE_FECHA_INVALIDA) from None


class FormularioDePeriodo(FlaskForm):
    class Meta:
        csrf = False

    desde = CampoDeFecha("Desde", validators=[InputRequired("Elegí la fecha de inicio.")])
    hasta = CampoDeFecha("Hasta", validators=[InputRequired("Elegí la fecha de fin.")])

    def validate_desde(self, campo: CampoDeFecha) -> None:
        # Un periodo de un solo dia (desde == hasta) es valido.
        if campo.data and self.hasta.data and campo.data > self.hasta.data:
            raise ValidationError(MENSAJE_PERIODO_INVERTIDO)

    def periodo(self) -> Periodo:
        """El periodo elegido. Solo se llama despues de `validate()`."""
        return Periodo(desde=self.desde.data, hasta=self.hasta.data)


MENSAJE_GRAVEDAD_INVALIDA = "Elegí un nivel de gravedad de la lista."


class FormularioDeGravedad(FlaskForm):
    """Filtro de gravedad de la seccion "Emergencias". Vacio significa "todas"."""

    class Meta:
        csrf = False

    gravedad = SelectField(
        "Nivel de gravedad",
        choices=[("", "Todas"), *((n.value, etiqueta_gravedad(n)) for n in NivelGravedad)],
        default="",
        validate_choice=False,
        validators=[Optional()],
    )

    def validate_gravedad(self, campo: SelectField) -> None:
        if campo.data and campo.data not in {nivel.value for nivel in NivelGravedad}:
            raise ValidationError(MENSAJE_GRAVEDAD_INVALIDA)

    def gravedad_elegida(self) -> NivelGravedad | None:
        """El nivel elegido, o None para todos. Solo se llama despues de `validate()`."""
        return NivelGravedad(self.gravedad.data) if self.gravedad.data else None
