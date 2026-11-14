"""Catalogo de las secciones del panel de auditoria y de sus indicadores exportables.

Una seccion es una pestaña del panel: su ruta, su plantilla, sus filtros propios y la funcion que
calcula sus datos. Cada indicador de la seccion (un grafico) se puede exportar, y su tabla sale
del mismo resultado que dibuja el grafico. Asi lo exportado coincide siempre con lo que se ve.

Para sumar una seccion: escribir su `obtener_seccion_de_*`, declararla aca y agregar su ruta en
`rutas.py` (una linea que llama a `_renderizar_seccion`). La pestaña y la exportacion aparecen
solas.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.modulos.indicadores import (
    convocatorias,
    proceso,
    recursos,
    red_de_ongs,
    respuesta,
    servicios,
)
from app.modulos.indicadores.exportacion import TablaExportable
from app.modulos.indicadores.formularios import (
    FiltroDeSeccion,
    FormularioDeDecision,
    FormularioDeGravedad,
    FormularioDeOrden,
    FormularioDeRubro,
)


@dataclass(frozen=True, slots=True)
class IndicadorExportable:
    """Un indicador que se puede descargar: su nombre en la URL y en el archivo, y su tabla."""

    slug: str
    titulo: str
    tabla: Callable[[Any], TablaExportable]


@dataclass(frozen=True, slots=True)
class SeccionDelPanel:
    """Una pestaña del panel.

    `obtener(periodo, **filtros)` calcula los datos; cada filtro llega con el nombre de su campo
    (`gravedad`, `rubro`, `orden`). El resultado tiene `a_diccionario()` para JSON, que viaja al
    lado del periodo o, con `clave_json`, bajo esa clave.
    """

    endpoint: str
    titulo: str
    icono: str
    plantilla: str
    obtener: Callable[..., Any]
    filtros: tuple[type[FiltroDeSeccion], ...] = ()
    indicadores: tuple[IndicadorExportable, ...] = ()
    clave_json: str | None = None


RESUMEN = SeccionDelPanel(
    endpoint="indicadores.panel",
    titulo="Resumen",
    icono="grafico",
    plantilla="indicadores/panel.html",
    obtener=servicios.obtener_resumen_de_actividad,
    clave_json="resumen",
    indicadores=(
        IndicadorExportable(
            "resumen-de-actividad", "Resumen de actividad", servicios.ResumenDeActividad.tabla
        ),
    ),
)

EMERGENCIAS = SeccionDelPanel(
    endpoint="indicadores.emergencias",
    titulo="Emergencias",
    icono="advertencia",
    plantilla="indicadores/emergencias.html",
    obtener=servicios.obtener_seccion_de_emergencias,
    filtros=(FormularioDeGravedad,),
    indicadores=(
        IndicadorExportable(
            "emergencias-por-estado",
            "Emergencias por estado",
            servicios.SeccionDeEmergencias.tabla_por_estado,
        ),
        IndicadorExportable(
            "cobertura-de-finalizadas",
            "Cobertura de las finalizadas",
            servicios.SeccionDeEmergencias.tabla_de_cobertura,
        ),
    ),
)

CONVOCATORIAS = SeccionDelPanel(
    endpoint="indicadores.convocatorias",
    titulo="Convocatorias",
    icono="lista",
    plantilla="indicadores/convocatorias.html",
    obtener=convocatorias.obtener_seccion_de_convocatorias,
    filtros=(FormularioDeDecision,),
    indicadores=(
        IndicadorExportable(
            "decisiones-de-cobertura",
            "Decisiones ante cobertura insuficiente",
            convocatorias.SeccionDeConvocatorias.tabla,
        ),
        IndicadorExportable(
            "emergencias-con-cobertura-insuficiente",
            "Emergencias con cobertura insuficiente",
            convocatorias.SeccionDeConvocatorias.tabla_de_detalle,
        ),
    ),
)

RECURSOS = SeccionDelPanel(
    endpoint="indicadores.recursos",
    titulo="Recursos",
    icono="capas",
    plantilla="indicadores/recursos.html",
    obtener=recursos.obtener_seccion_de_recursos,
    filtros=(FormularioDeRubro,),
    indicadores=(
        IndicadorExportable(
            "recursos-movilizados",
            "Recursos movilizados por mes y rubro",
            lambda seccion: seccion.movilizados.tabla(),
        ),
        IndicadorExportable(
            "rubros-demanda-e-inhabilitacion",
            "Demanda por rubro e inhabilitación del Sistema Nacional",
            lambda seccion: seccion.rubros.tabla(),
        ),
    ),
)

RED_DE_ONGS = SeccionDelPanel(
    endpoint="indicadores.red_de_ongs",
    titulo="Red de ONGs",
    icono="organizaciones",
    plantilla="indicadores/red_de_ongs.html",
    obtener=red_de_ongs.obtener_seccion_de_red_de_ongs,
    filtros=(FormularioDeOrden,),
    indicadores=(
        IndicadorExportable(
            "consorcios",
            "Adjudicaciones de consorcios e individuales",
            lambda seccion: seccion.consorcios.tabla(),
        ),
        IndicadorExportable(
            "ranking-de-ongs", "Ranking de ONGs", lambda seccion: seccion.ranking.tabla()
        ),
    ),
)

TIEMPOS_DE_RESPUESTA = SeccionDelPanel(
    endpoint="indicadores.tiempos_de_respuesta",
    titulo="Tiempos de respuesta",
    icono="reloj",
    plantilla="indicadores/tiempos_de_respuesta.html",
    obtener=respuesta.obtener_seccion_de_tiempos,
    indicadores=(
        IndicadorExportable(
            "tiempos-de-respuesta",
            "Tiempo medio entre la alerta y la adjudicación",
            respuesta.SeccionDeTiempos.tabla,
        ),
    ),
)

PROCESO = SeccionDelPanel(
    endpoint="indicadores.proceso",
    titulo="Proceso",
    icono="flujo",
    plantilla="indicadores/proceso.html",
    obtener=proceso.obtener_seccion_de_proceso,
    filtros=(FormularioDeGravedad,),
    indicadores=(
        IndicadorExportable(
            "etapas-del-proceso",
            "Tiempo promedio de cada etapa del proceso",
            lambda seccion: seccion.etapas.tabla(),
        ),
        IndicadorExportable(
            "resolucion-en-termino",
            "Resolución en término según gravedad",
            lambda seccion: seccion.resolucion.tabla(),
        ),
    ),
)

# En el orden de las pestañas.
SECCIONES: tuple[SeccionDelPanel, ...] = (
    RESUMEN,
    EMERGENCIAS,
    CONVOCATORIAS,
    RECURSOS,
    RED_DE_ONGS,
    TIEMPOS_DE_RESPUESTA,
    PROCESO,
)


def _indexar_indicadores() -> dict[str, tuple[SeccionDelPanel, IndicadorExportable]]:
    indice: dict[str, tuple[SeccionDelPanel, IndicadorExportable]] = {}
    for seccion in SECCIONES:
        for indicador in seccion.indicadores:
            if indicador.slug in indice:
                raise ValueError(f"Indicador exportable repetido: {indicador.slug}")
            indice[indicador.slug] = (seccion, indicador)
    return indice


INDICADORES_EXPORTABLES = _indexar_indicadores()
