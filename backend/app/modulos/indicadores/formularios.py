"""Formularios del panel de auditoria.

Los filtros viajan por GET, en la query string: la URL de un periodo se puede compartir
y el boton "atras" del navegador funciona. Al ser una consulta de solo lectura, no lleva CSRF.

Ademas del periodo, que comparten todas las secciones, cada seccion puede tener filtros propios
(`FiltroDeSeccion`): un unico campo de seleccion cuyo nombre es el del parametro de la URL. Un
valor fuera de la lista no se aplica y vuelve con su error, igual que un periodo invalido.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from typing import Any, ClassVar

from flask_wtf import FlaskForm
from wtforms import DateField, SelectField
from wtforms.validators import InputRequired, Optional, ValidationError

from app.core.interfaz.plantillas import etiqueta_gravedad, etiqueta_tipo_necesidad
from app.modulos.emergencias.modelos import NivelGravedad, TipoNecesidad
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


# --- Filtros propios de una seccion ----------------------------------------------


class FiltroDeSeccion(FlaskForm):
    """Base de los filtros de una seccion: un `SelectField` llamado `campo` sobre un enum.

    Vacio significa "todos" (o el valor por defecto). Cada subclase declara su campo con el mismo
    nombre que `campo` y lo valida con `_validar_opcion`.
    """

    class Meta:
        csrf = False

    campo: ClassVar[str]
    opciones: ClassVar[type[enum.Enum]]
    # Valor que rige cuando el campo llega vacio; None es "todos".
    por_defecto: ClassVar[enum.Enum | None] = None

    @classmethod
    def _choices(
        cls, opciones: type[enum.Enum], etiquetar: Callable[[Any], str], todos: str | None
    ) -> list[tuple[str, str]]:
        primero = [("", todos)] if todos else []
        return [*primero, *((opcion.value, etiquetar(opcion)) for opcion in opciones)]

    def _validar_opcion(self, campo: SelectField, mensaje: str) -> None:
        if campo.data and campo.data not in {opcion.value for opcion in self.opciones}:
            raise ValidationError(mensaje)

    def elegido(self) -> enum.Enum | None:
        """La opcion elegida, o `por_defecto` si no hay. Solo se llama despues de `validate()`."""
        dato = self[self.campo].data
        return self.opciones(dato) if dato else self.por_defecto

    def valor_valido(self) -> enum.Enum | None:
        """La opcion elegida si el filtro es valido; si no, `por_defecto` (no se aplica)."""
        return self.elegido() if self.validate() else self.por_defecto

    def aplicado(self, valor: enum.Enum | None) -> dict[str, str]:
        """El filtro como parametro de URL, para que los demas enlaces lo conserven.

        El valor por defecto no viaja: la URL "limpia" ya lo implica.
        """
        if valor is None or valor == self.por_defecto:
            return {}
        return {self.campo: valor.value}


MENSAJE_GRAVEDAD_INVALIDA = "Elegí un nivel de gravedad de la lista."


class FormularioDeGravedad(FiltroDeSeccion):
    """Filtro de gravedad. Vacio significa "todas"."""

    campo = "gravedad"
    opciones = NivelGravedad

    gravedad = SelectField(
        "Nivel de gravedad",
        choices=FiltroDeSeccion._choices(NivelGravedad, etiqueta_gravedad, "Todas"),
        default="",
        validate_choice=False,
        validators=[Optional()],
    )

    def validate_gravedad(self, campo: SelectField) -> None:
        self._validar_opcion(campo, MENSAJE_GRAVEDAD_INVALIDA)

    def gravedad_elegida(self) -> NivelGravedad | None:
        """El nivel elegido, o None para todos. Solo se llama despues de `validate()`."""
        return self.elegido()


MENSAJE_RUBRO_INVALIDO = "Elegí un rubro de la lista."


class FormularioDeRubro(FiltroDeSeccion):
    """Filtro de rubro (la categoria de los items). Vacio significa "todos"."""

    campo = "rubro"
    opciones = TipoNecesidad

    rubro = SelectField(
        "Rubro",
        choices=FiltroDeSeccion._choices(TipoNecesidad, etiqueta_tipo_necesidad, "Todos"),
        default="",
        validate_choice=False,
        validators=[Optional()],
    )

    def validate_rubro(self, campo: SelectField) -> None:
        self._validar_opcion(campo, MENSAJE_RUBRO_INVALIDO)


class OrdenDelRanking(enum.Enum):
    """Como se ordena la tabla del ranking de ONGs."""

    volumen = "volumen"
    tiempo = "tiempo"


ETIQUETA_POR_ORDEN = {
    OrdenDelRanking.volumen: "Lotes adjudicados",
    OrdenDelRanking.tiempo: "Tiempo medio de ejecución",
}

MENSAJE_ORDEN_INVALIDO = "Elegí un orden de la lista."


class FormularioDeOrden(FiltroDeSeccion):
    """Orden de la tabla del ranking. Vacio es por volumen, el orden del grafico."""

    campo = "orden"
    opciones = OrdenDelRanking
    por_defecto = OrdenDelRanking.volumen

    orden = SelectField(
        "Ordenar por",
        choices=FiltroDeSeccion._choices(OrdenDelRanking, ETIQUETA_POR_ORDEN.__getitem__, None),
        default="",
        validate_choice=False,
        validators=[Optional()],
    )

    def validate_orden(self, campo: SelectField) -> None:
        self._validar_opcion(campo, MENSAJE_ORDEN_INVALIDO)
