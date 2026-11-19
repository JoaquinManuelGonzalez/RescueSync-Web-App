"""Definiciones de graficos del panel, del lado del servidor.

Arman el JSON que dibuja `frontend/estaticos/js/graficos.js` (su encabezado documenta el
contrato) y que el macro `tarjeta_grafico()` publica en la pagina. Armarlas en Python y no en la
plantilla deja un solo lugar donde se decide que se grafica, y permite verificarlas en los tests
sin navegador (ADR-010).

Criterios de lectura que siguen todos los graficos del panel:

- Un solo eje de valores: dos medidas de escala distinta van en dos graficos, nunca en un doble
  eje que invita a comparar alturas que no son comparables.
- Barras horizontales cuando las etiquetas son largas (ONGs, rubros, etapas).
- El valor escrito al final de cada barra (`mostrar_valores`), para leer el grafico sin pasar el
  mouse ni consultar la tabla.
- Los colores se piden por tono, nunca en hexadecimal. Los tonos `serie-1` a `serie-8` son la
  paleta categorica validada para daltonismo; el color sigue a la entidad (un rubro, una
  gravedad) y no a su posicion en el ranking.
- Las duraciones (`barras_de_duracion`) se dibujan en la unidad que mejor se lee para el valor
  mas alto (minutos, horas o dias) y cada valor lleva su texto exacto, formateado aca: el
  navegador no redondea ni elige como escribir un tiempo.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from app.modulos.emergencias.modelos import NivelGravedad, TipoNecesidad
from app.modulos.indicadores.tiempos import (
    UNIDADES_DE_TIEMPO,
    UnidadDeTiempo,
    duracion_abreviada,
    duracion_como_texto,
)

Unidad = tuple[str, str]

PORCIENTO: Unidad = ("%", "%")

# Cada rubro conserva su color en todos los graficos y con cualquier filtro.
TONO_POR_RUBRO: dict[TipoNecesidad, str] = {
    rubro: f"serie-{indice}" for indice, rubro in enumerate(TipoNecesidad, start=1)
}

# Los mismos colores que los puntos de gravedad de los filtros (indicadores.css).
TONO_POR_GRAVEDAD: dict[NivelGravedad, str] = {
    NivelGravedad.baja: "neutro",
    NivelGravedad.media: "info",
    NivelGravedad.alta: "advertencia",
    NivelGravedad.critica: "primario",
}


def _numero(valor: Any) -> Any:
    """Decimal no es serializable a JSON: viaja como float, ya redondeado por el servicio."""
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


@dataclass(frozen=True, slots=True)
class Serie:
    """Una serie de un grafico de barras apiladas (todas sobre el mismo eje)."""

    nombre: str
    valores: Sequence[Any]
    tono: str
    unidad: Unidad
    decimales: int = 0

    def a_diccionario(self) -> dict[str, Any]:
        return {
            "nombre": self.nombre,
            "valores": [_numero(valor) for valor in self.valores],
            "tono": self.tono,
            "unidad": list(self.unidad),
            "decimales": self.decimales,
        }


@dataclass(frozen=True, slots=True)
class Marcadores:
    """Una referencia por barra, dibujada como una marca horizontal sobre el mismo eje.

    Sirve para comparar cada valor con su objetivo (el tiempo medio con el plazo de su gravedad).
    `textos`, si se indica, es lo que muestra el tooltip de cada marca en lugar del numero.
    """

    nombre: str
    valores: Sequence[Any]
    textos: Sequence[str] | None = None

    def a_diccionario(self) -> dict[str, Any]:
        definicion: dict[str, Any] = {
            "nombre": self.nombre,
            "valores": [_numero(valor) for valor in self.valores],
        }
        if self.textos is not None:
            definicion["textos"] = list(self.textos)
        return definicion


def barras(
    etiquetas: Sequence[str],
    valores: Sequence[Any],
    *,
    tonos: Sequence[str],
    unidad: Unidad,
    detalles: Sequence[str | None] | None = None,
    horizontal: bool = False,
    decimales: int = 0,
    sin_dato: str | None = None,
    mostrar_valores: bool = True,
    maximo: float | None = None,
    marcadores: Marcadores | None = None,
    enlaces: Sequence[str] | None = None,
    textos: Sequence[str | None] | None = None,
    textos_cortos: Sequence[str | None] | None = None,
    unidad_del_eje: str | None = None,
) -> dict[str, Any]:
    """Barras de una sola serie, con un color por barra.

    Un valor None es "sin dato": no dibuja barra y, con `sin_dato`, escribe ese texto en su
    lugar ("Sin ocurrencias"), para que no se confunda con un cero. `maximo` fija el tope del eje
    (100 para porcentajes).

    `enlaces`, una URL por barra, hace que tocar una barra aplique el filtro de la seccion que
    lleva a esa URL (el mismo enlace del filtro segmentado, que sigue siendo el camino accesible
    con teclado y sin JavaScript).

    `textos` (el tooltip) y `textos_cortos` (la etiqueta sobre la barra) reemplazan al numero
    cuando el servidor ya sabe como escribir cada valor; `unidad_del_eje` acompaña a los numeros
    del eje ("12 h"). Los usa `barras_de_duracion`.
    """
    definicion: dict[str, Any] = {
        "tipo": "barras",
        "etiquetas": list(etiquetas),
        "valores": [_numero(valor) for valor in valores],
        "tonos": list(tonos),
        "unidad": list(unidad),
        "decimales": decimales,
        "mostrarValores": mostrar_valores,
    }
    if detalles is not None:
        definicion["detalles"] = list(detalles)
    if horizontal:
        definicion["orientacion"] = "horizontal"
    if sin_dato is not None:
        definicion["sinDato"] = sin_dato
    if maximo is not None:
        definicion["maximo"] = maximo
    if marcadores is not None:
        definicion["marcadores"] = marcadores.a_diccionario()
    if enlaces is not None:
        definicion["enlaces"] = list(enlaces)
    if textos is not None:
        definicion["textos"] = list(textos)
    if textos_cortos is not None:
        definicion["textosCortos"] = list(textos_cortos)
    if unidad_del_eje is not None:
        definicion["unidadDelEje"] = unidad_del_eje
    return definicion


def escala_para(duraciones: Iterable[timedelta | None]) -> UnidadDeTiempo:
    """La mayor unidad en la que la duracion mas larga vale al menos 2.

    Deja el eje en numeros comodos: hasta 1 h 59 min se lee en minutos y hasta 47 h en horas, en
    vez de "1,9 h" o "1,9 d". Sin duraciones, segundos.
    """
    maxima = max((duracion for duracion in duraciones if duracion is not None), default=None)
    if maxima is None:
        return UNIDADES_DE_TIEMPO[-1]
    return next(
        (unidad for unidad in UNIDADES_DE_TIEMPO if maxima >= 2 * unidad.tamano),
        UNIDADES_DE_TIEMPO[-1],
    )


def _en_escala(duracion: timedelta | None, escala: UnidadDeTiempo) -> float | None:
    return None if duracion is None else round(duracion / escala.tamano, 3)


def barras_de_duracion(
    etiquetas: Sequence[str],
    duraciones: Sequence[timedelta | None],
    *,
    tonos: Sequence[str],
    detalles: Sequence[str | None] | None = None,
    horizontal: bool = False,
    sin_dato: str | None = None,
    marcadores: Marcadores | None = None,
) -> dict[str, Any]:
    """Barras de duraciones (`timedelta`, o None sin dato), como `barras`.

    El eje queda en la unidad de `escala_para`, elegida con las barras y las marcas, y sus
    numeros llevan la abreviatura ("12 h"). Sobre cada barra va la duracion abreviada
    ("1 d 4 h") y en el tooltip, la completa ("1 d 4 h 12 min 5 s"). Los valores de `marcadores`
    tambien son `timedelta`.
    """
    valores_de_marcas = marcadores.valores if marcadores else ()
    escala = escala_para([*duraciones, *valores_de_marcas])
    return barras(
        etiquetas,
        [_en_escala(duracion, escala) for duracion in duraciones],
        tonos=tonos,
        unidad=(escala.abreviatura, escala.abreviatura),
        detalles=detalles,
        horizontal=horizontal,
        decimales=1,
        sin_dato=sin_dato,
        marcadores=(
            Marcadores(
                marcadores.nombre,
                [_en_escala(valor, escala) for valor in valores_de_marcas],
                textos=[duracion_como_texto(valor) for valor in valores_de_marcas],
            )
            if marcadores
            else None
        ),
        textos=[duracion_como_texto(d) if d is not None else None for d in duraciones],
        textos_cortos=[duracion_abreviada(d) if d is not None else None for d in duraciones],
        unidad_del_eje=escala.abreviatura,
    )


def barras_apiladas(etiquetas: Sequence[str], series: Sequence[Serie]) -> dict[str, Any]:
    """Una barra por etiqueta con un segmento por serie; el tooltip suma el total."""
    return {
        "tipo": "barras",
        "etiquetas": list(etiquetas),
        "series": [serie.a_diccionario() for serie in series],
        "apilado": True,
    }


def dona(
    etiquetas: Sequence[str],
    valores: Sequence[int],
    *,
    porcentajes: Sequence[int],
    tonos: Sequence[str],
    unidad: Unidad,
) -> dict[str, Any]:
    return {
        "tipo": "dona",
        "etiquetas": list(etiquetas),
        "valores": list(valores),
        "porcentajes": list(porcentajes),
        "tonos": list(tonos),
        "unidad": list(unidad),
    }
