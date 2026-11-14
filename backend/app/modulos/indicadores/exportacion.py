"""Exportacion de los indicadores a CSV y JSON, sin base de datos ni Flask.

Cada indicador se reduce a una `TablaExportable`: columnas con nombre y filas de valores. La
misma tabla alimenta el CSV, el JSON y la tabla de respaldo del grafico, asi lo exportado es
exactamente lo que se ve (regla de negocio de la HU de exportacion).

Formato:

- CSV en UTF-8, separado por comas, con los encabezados en la primera fila. Sin datos, sale solo
  esa fila. Los decimales usan punto (la coma ya es el separador) y las fechas, ISO 8601. Empieza
  con la marca de orden de bytes (BOM) de UTF-8: sin ella, Excel en Windows abre el archivo como
  Latin-1 y rompe los acentos ("Crítica"). Las demas planillas y librerias la ignoran.
- JSON con los filtros aplicados y el arreglo de datos, una entrada por fila.
"""

from __future__ import annotations

import csv
import enum
import io
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.modulos.indicadores.periodo import Periodo

PREFIJO_DE_ARCHIVO = "rescuesync"
BOM_UTF8 = "\ufeff"


@dataclass(frozen=True, slots=True)
class TablaExportable:
    """Los datos de un indicador: nombres de columna y una tupla de valores por fila."""

    columnas: tuple[str, ...]
    filas: tuple[tuple[Any, ...], ...] = ()

    def __post_init__(self) -> None:
        for fila in self.filas:
            if len(fila) != len(self.columnas):
                raise ValueError("Cada fila debe tener un valor por columna.")

    @property
    def vacia(self) -> bool:
        return not self.filas

    def como_diccionarios(self) -> list[dict[str, Any]]:
        return [dict(zip(self.columnas, fila, strict=True)) for fila in self.filas]

    def como_json(self) -> list[dict[str, Any]]:
        """Las filas como diccionarios con valores aptos para JSON (decimales como numeros)."""
        return [
            {columna: _valor_para_json(valor) for columna, valor in fila.items()}
            for fila in self.como_diccionarios()
        ]


def _valor_para_csv(valor: Any) -> Any:
    if valor is None:
        return ""
    return _valor_para_json(valor)


def _valor_para_json(valor: Any) -> Any:
    if isinstance(valor, enum.Enum):
        return valor.value
    if isinstance(valor, datetime | date):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        # Un decimal con su escala ("5.0") se lee igual en una planilla y en JSON.
        return float(valor)
    return valor


def a_csv(tabla: TablaExportable) -> str:
    salida = io.StringIO()
    salida.write(BOM_UTF8)
    escritor = csv.writer(salida, lineterminator="\r\n")
    escritor.writerow(tabla.columnas)
    for fila in tabla.filas:
        escritor.writerow(_valor_para_csv(valor) for valor in fila)
    return salida.getvalue()


def a_json(
    *,
    indicador: str,
    titulo: str,
    filtros: Mapping[str, Any],
    tabla: TablaExportable,
    generado_en: datetime,
) -> dict[str, Any]:
    return {
        "indicador": indicador,
        "titulo": titulo,
        "generado_en": generado_en.isoformat(),
        "filtros": {nombre: _valor_para_json(valor) for nombre, valor in filtros.items()},
        "columnas": list(tabla.columnas),
        "datos": tabla.como_json(),
    }


def nombre_de_archivo(slug: str, periodo: Periodo, extension: str) -> str:
    """`rescuesync-recursos-movilizados-2026-09-01_2026-10-31.csv`."""
    return (
        f"{PREFIJO_DE_ARCHIVO}-{slug}-{periodo.desde.isoformat()}_{periodo.hasta.isoformat()}"
        f".{extension}"
    )
