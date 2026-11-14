"""Seccion "Red de ONGs" del panel de auditoria.

- Consorcios: que parte de las ofertas adjudicadas fue de consorcios y que parte individual, y
  cuantas emergencias contaron con al menos un consorcio.
- Ranking de ONGs: lotes adjudicados a cada ONG y cuanto tarda en finalizar sus actividades.

Una oferta es de consorcio si tiene mas de una ONG participante aceptada. En un consorcio
adjudicado, cada lote cuenta para cada ONG participante.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.modulos.adjudicaciones import servicios as servicios_de_adjudicaciones
from app.modulos.adjudicaciones.servicios import OfertaAdjudicada
from app.modulos.ejecucion_cierre import servicios as servicios_de_ejecucion
from app.modulos.emergencias import servicios as servicios_de_emergencias
from app.modulos.indicadores import graficos
from app.modulos.indicadores.cobertura import porcentajes_que_suman_100
from app.modulos.indicadores.exportacion import TablaExportable
from app.modulos.indicadores.formularios import OrdenDelRanking
from app.modulos.indicadores.periodo import Periodo
from app.modulos.indicadores.tiempos import (
    dias_como_texto,
    duracion_en_dias,
    porcentaje_entero,
    promedio_en_dias,
)
from app.modulos.organizaciones import servicios as servicios_de_organizaciones

OFERTAS: graficos.Unidad = ("oferta", "ofertas")
LOTES: graficos.Unidad = ("lote", "lotes")

# El grafico del ranking muestra las primeras; la tabla, todas.
ONGS_EN_EL_GRAFICO = 10

# --- Consorcios ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Consorcios:
    """Ofertas adjudicadas de consorcio e individuales, y emergencias con algun consorcio."""

    de_consorcio: int
    individuales: int
    emergencias_con_adjudicacion: int
    emergencias_con_consorcio: int

    @property
    def adjudicadas(self) -> int:
        return self.de_consorcio + self.individuales

    @property
    def porcentajes(self) -> tuple[int, int]:
        """Porcentaje de consorcio e individual, que siempre suman 100 (o 0 sin ofertas)."""
        consorcio, individual = porcentajes_que_suman_100([self.de_consorcio, self.individuales])
        return consorcio, individual

    @property
    def porcentaje_de_emergencias_con_consorcio(self) -> int | None:
        return porcentaje_entero(self.emergencias_con_consorcio, self.emergencias_con_adjudicacion)

    def porciones(self) -> list[tuple[str, int, int, str]]:
        """(etiqueta, ofertas, porcentaje, tono) de cada porcion de la torta."""
        consorcio, individual = self.porcentajes
        return [
            ("Consorcio", self.de_consorcio, consorcio, "serie-1"),
            ("Individual", self.individuales, individual, "serie-2"),
        ]

    def grafico(self) -> dict[str, Any]:
        porciones = self.porciones()
        return graficos.dona(
            [etiqueta for etiqueta, *_ in porciones],
            [cantidad for _, cantidad, _, _ in porciones],
            porcentajes=[porcentaje for _, _, porcentaje, _ in porciones],
            tonos=[tono for *_, tono in porciones],
            unidad=OFERTAS,
        )

    def tabla(self) -> TablaExportable:
        return TablaExportable(
            columnas=("tipo_de_oferta", "ofertas_adjudicadas", "porcentaje"),
            filas=tuple(
                (etiqueta, cantidad, porcentaje)
                for etiqueta, cantidad, porcentaje, _ in self.porciones()
            )
            if self.adjudicadas
            else (),
        )

    def a_diccionario(self) -> dict[str, Any]:
        return {
            "ofertas_adjudicadas": self.adjudicadas,
            "emergencias_con_adjudicacion": self.emergencias_con_adjudicacion,
            "emergencias_con_consorcio": self.emergencias_con_consorcio,
            "porcentaje_de_emergencias_con_consorcio": self.porcentaje_de_emergencias_con_consorcio,
            "datos": self.tabla().como_json(),
        }


def _consorcios(ofertas: list[OfertaAdjudicada]) -> Consorcios:
    de_consorcio = sum(oferta.es_de_consorcio for oferta in ofertas)
    return Consorcios(
        de_consorcio=de_consorcio,
        individuales=len(ofertas) - de_consorcio,
        emergencias_con_adjudicacion=len({oferta.emergencia_id for oferta in ofertas}),
        emergencias_con_consorcio=len(
            {oferta.emergencia_id for oferta in ofertas if oferta.es_de_consorcio}
        ),
    )


# --- Ranking de ONGs -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FilaDelRanking:
    """Una ONG del ranking.

    `tiempo_medio_de_ejecucion` son los dias entre la adjudicacion y la finalizacion de cada
    actividad, promediados; None si todavia no finalizo ninguna.
    """

    organizacion_id: int
    nombre: str
    lotes_adjudicados: int
    actividades_finalizadas: int
    tiempo_medio_de_ejecucion: Decimal | None

    @property
    def tiempo_como_texto(self) -> str:
        return dias_como_texto(self.tiempo_medio_de_ejecucion)


def _por_volumen(fila: FilaDelRanking) -> tuple:
    return (-fila.lotes_adjudicados, fila.nombre.casefold())


def _por_tiempo(fila: FilaDelRanking) -> tuple:
    """De menor a mayor tiempo; las que no tienen valor, al final (y entre ellas, por volumen)."""
    sin_valor = fila.tiempo_medio_de_ejecucion is None
    return (sin_valor, fila.tiempo_medio_de_ejecucion or Decimal(0), *_por_volumen(fila))


CLAVE_POR_ORDEN = {OrdenDelRanking.volumen: _por_volumen, OrdenDelRanking.tiempo: _por_tiempo}


@dataclass(frozen=True, slots=True)
class RankingDeOngs:
    """Las ONGs con adjudicaciones en el periodo, en el orden pedido para la tabla."""

    orden: OrdenDelRanking
    filas: tuple[FilaDelRanking, ...]

    @property
    def primeras_por_volumen(self) -> tuple[FilaDelRanking, ...]:
        return tuple(sorted(self.filas, key=_por_volumen)[:ONGS_EN_EL_GRAFICO])

    def grafico(self) -> dict[str, Any]:
        primeras = self.primeras_por_volumen
        return graficos.barras(
            [fila.nombre for fila in primeras],
            [fila.lotes_adjudicados for fila in primeras],
            tonos=["serie-1"] * len(primeras),
            unidad=LOTES,
            detalles=[f"Tiempo medio de ejecución: {fila.tiempo_como_texto}" for fila in primeras],
            horizontal=True,
        )

    def tabla(self) -> TablaExportable:
        return TablaExportable(
            columnas=(
                "posicion",
                "ong",
                "lotes_adjudicados",
                "actividades_finalizadas",
                "tiempo_medio_de_ejecucion_dias",
            ),
            filas=tuple(
                (
                    posicion,
                    fila.nombre,
                    fila.lotes_adjudicados,
                    fila.actividades_finalizadas,
                    fila.tiempo_medio_de_ejecucion,
                )
                for posicion, fila in enumerate(self.filas, start=1)
            ),
        )

    def a_diccionario(self) -> dict[str, Any]:
        return {"orden": self.orden.value, "datos": self.tabla().como_json()}


def _ranking(
    ofertas: list[OfertaAdjudicada], emergencia_ids, orden: OrdenDelRanking
) -> RankingDeOngs:
    lotes_por_ong: dict[int, set[int]] = defaultdict(set)
    adjudicada_en_por_oferta = {}
    for oferta in ofertas:
        adjudicada_en_por_oferta[oferta.oferta_id] = oferta.adjudicada_en
        for organizacion_id in oferta.organizacion_ids:
            lotes_por_ong[organizacion_id] |= oferta.lote_ids

    duraciones_por_ong: dict[int, list[Decimal]] = defaultdict(list)
    for finalizacion in servicios_de_ejecucion.listar_finalizaciones(emergencia_ids=emergencia_ids):
        adjudicada_en = adjudicada_en_por_oferta.get(finalizacion.oferta_id)
        if adjudicada_en is not None and finalizacion.organizacion_id in lotes_por_ong:
            duraciones_por_ong[finalizacion.organizacion_id].append(
                duracion_en_dias(adjudicada_en, finalizacion.fecha_fin)
            )

    nombres = servicios_de_organizaciones.obtener_nombres(lotes_por_ong)
    filas = [
        FilaDelRanking(
            organizacion_id=organizacion_id,
            nombre=nombres.get(organizacion_id, f"Organización {organizacion_id}"),
            lotes_adjudicados=len(lotes),
            actividades_finalizadas=len(duraciones_por_ong[organizacion_id]),
            tiempo_medio_de_ejecucion=promedio_en_dias(duraciones_por_ong[organizacion_id]),
        )
        for organizacion_id, lotes in lotes_por_ong.items()
    ]
    return RankingDeOngs(orden=orden, filas=tuple(sorted(filas, key=CLAVE_POR_ORDEN[orden])))


# --- La seccion ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SeccionDeRedDeOngs:
    consorcios: Consorcios
    ranking: RankingDeOngs

    def a_diccionario(self) -> dict[str, Any]:
        return {
            "filtros": {"orden": self.ranking.orden.value},
            "consorcios": self.consorcios.a_diccionario(),
            "ranking": self.ranking.a_diccionario(),
        }


def obtener_seccion_de_red_de_ongs(
    periodo: Periodo, orden: OrdenDelRanking = OrdenDelRanking.volumen
) -> SeccionDeRedDeOngs:
    """Consorcios y ranking de ONGs sobre las emergencias registradas en el periodo."""
    desde, hasta = periodo.limites_utc()
    emergencia_ids = servicios_de_emergencias.consultar_ids_de_emergencias_registradas(
        desde=desde, hasta=hasta
    )
    ofertas = servicios_de_adjudicaciones.listar_ofertas_adjudicadas(emergencia_ids=emergencia_ids)
    return SeccionDeRedDeOngs(
        consorcios=_consorcios(ofertas),
        ranking=_ranking(ofertas, emergencia_ids, orden),
    )
