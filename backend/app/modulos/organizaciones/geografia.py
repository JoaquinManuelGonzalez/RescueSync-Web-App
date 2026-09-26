"""Vocabulario geografico de las zonas de cobertura.

La provincia es una lista cerrada y la localidad es texto libre. La provincia se cierra porque es
lo que permite filtrar y comparar coberturas sin depender de como la escribio cada persona; la
localidad queda abierta porque no hay en el sistema un catalogo oficial de partidos y localidades
(la API Georef del INDEC seria la fuente si alguna vez hace falta validarla).

No importa nada del resto de la aplicacion: lo usan los modelos, los formularios, los servicios y
las plantillas por igual.
"""

from __future__ import annotations

# Las 24 jurisdicciones de primer orden de la Republica Argentina, en orden alfabetico.
PROVINCIAS: tuple[str, ...] = (
    "Buenos Aires",
    "Catamarca",
    "Chaco",
    "Chubut",
    "Ciudad Autónoma de Buenos Aires",
    "Córdoba",
    "Corrientes",
    "Entre Ríos",
    "Formosa",
    "Jujuy",
    "La Pampa",
    "La Rioja",
    "Mendoza",
    "Misiones",
    "Neuquén",
    "Río Negro",
    "Salta",
    "San Juan",
    "San Luis",
    "Santa Cruz",
    "Santa Fe",
    "Santiago del Estero",
    "Tierra del Fuego, Antártida e Islas del Atlántico Sur",
    "Tucumán",
)

# (valor, texto) para los select de la interfaz: el valor es el nombre oficial.
OPCIONES_DE_PROVINCIA: list[tuple[str, str]] = [(provincia, provincia) for provincia in PROVINCIAS]
