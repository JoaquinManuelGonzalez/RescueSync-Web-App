"""Seccion "Tiempos de respuesta" del panel de auditoria.

Cuanto tarda en promedio una emergencia desde que el municipio la registra hasta la primera
adjudicacion, por gravedad y en general. Mide la etapa en la que todavia no hay ayuda en camino.

Inicio = fecha de registro de la emergencia; fin = su primera adjudicacion registrada. Las
emergencias sin adjudicar no entran en el promedio y se informan aparte; las canceladas no se
cuentan como "sin adjudicar" porque nunca lo van a estar.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.core.interfaz.plantillas import etiqueta_gravedad
from app.modulos.convocatorias import servicios as servicios_de_convocatorias
from app.modulos.emergencias import servicios as servicios_de_emergencias
from app.modulos.emergencias.modelos import EstadoEmergencia, NivelGravedad
from app.modulos.indicadores import graficos
from app.modulos.indicadores.exportacion import TablaExportable
from app.modulos.indicadores.periodo import Periodo
from app.modulos.indicadores.tiempos import dias_como_texto, duracion_en_dias, promedio_en_dias

SIN_ADJUDICACIONES = "Sin adjudicaciones"


@dataclass(frozen=True, slots=True)
class TiempoDeGravedad:
    """El tiempo medio hasta la adjudicacion de las emergencias de una gravedad."""

    gravedad: NivelGravedad
    adjudicadas: int
    promedio: Decimal | None

    @property
    def etiqueta(self) -> str:
        return etiqueta_gravedad(self.gravedad)

    @property
    def promedio_como_texto(self) -> str:
        return dias_como_texto(self.promedio)


@dataclass(frozen=True, slots=True)
class SeccionDeTiempos:
    """Tiempo medio por gravedad (todas, en el orden del catalogo) y en general."""

    por_gravedad: tuple[TiempoDeGravedad, ...]
    promedio_general: Decimal | None
    sin_adjudicar: int

    @property
    def adjudicadas(self) -> int:
        return sum(fila.adjudicadas for fila in self.por_gravedad)

    @property
    def promedio_general_como_texto(self) -> str:
        return dias_como_texto(self.promedio_general)

    def grafico(self) -> dict[str, Any]:
        return graficos.barras(
            [fila.etiqueta for fila in self.por_gravedad],
            [fila.promedio for fila in self.por_gravedad],
            tonos=[graficos.TONO_POR_GRAVEDAD[fila.gravedad] for fila in self.por_gravedad],
            unidad=graficos.DIAS,
            detalles=[
                f"{fila.adjudicadas} {'emergencia' if fila.adjudicadas == 1 else 'emergencias'}"
                for fila in self.por_gravedad
            ],
            decimales=1,
            sin_dato=SIN_ADJUDICACIONES,
        )

    def tabla(self) -> TablaExportable:
        """Una fila por gravedad, como el grafico, y la del promedio general. Sin ninguna
        emergencia adjudicada no hay tiempos que informar y la tabla queda vacia."""
        columnas = ("gravedad", "emergencias_adjudicadas", "tiempo_medio_dias")
        if not self.adjudicadas:
            return TablaExportable(columnas=columnas)
        return TablaExportable(
            columnas=columnas,
            filas=(
                *((fila.etiqueta, fila.adjudicadas, fila.promedio) for fila in self.por_gravedad),
                ("General", self.adjudicadas, self.promedio_general),
            ),
        )

    def a_diccionario(self) -> dict[str, Any]:
        return {
            "promedio_general_dias": (
                float(self.promedio_general) if self.promedio_general is not None else None
            ),
            "adjudicadas": self.adjudicadas,
            "sin_adjudicar": self.sin_adjudicar,
            "datos": self.tabla().como_json(),
        }


def obtener_seccion_de_tiempos(periodo: Periodo) -> SeccionDeTiempos:
    """Tiempos entre la alerta y la adjudicacion de las emergencias registradas en el periodo."""
    desde, hasta = periodo.limites_utc()
    registros = servicios_de_emergencias.listar_registros_de_emergencias(desde=desde, hasta=hasta)
    primera_adjudicacion = servicios_de_convocatorias.obtener_primera_adjudicacion(
        emergencia_ids=servicios_de_emergencias.consultar_ids_de_emergencias_registradas(
            desde=desde, hasta=hasta
        )
    )

    duraciones: dict[NivelGravedad, list[Decimal]] = defaultdict(list)
    sin_adjudicar = 0
    for registro in registros:
        adjudicada_en = primera_adjudicacion.get(registro.id)
        if adjudicada_en is not None:
            duraciones[registro.nivel_gravedad].append(
                duracion_en_dias(registro.creado_en, adjudicada_en)
            )
        elif registro.estado != EstadoEmergencia.cancelada:
            sin_adjudicar += 1

    return SeccionDeTiempos(
        por_gravedad=tuple(
            TiempoDeGravedad(
                gravedad=gravedad,
                adjudicadas=len(duraciones[gravedad]),
                promedio=promedio_en_dias(duraciones[gravedad]),
            )
            for gravedad in NivelGravedad
        ),
        promedio_general=promedio_en_dias(d for lista in duraciones.values() for d in lista),
        sin_adjudicar=sin_adjudicar,
    )
