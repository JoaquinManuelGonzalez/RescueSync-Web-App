"""Seccion "Proceso" del panel de auditoria: datos del motor de procesos (Bonita).

- Etapas del proceso: cuanto tarda en promedio cada tarea humana, sobre los casos terminados.
- Resolucion en termino: por gravedad, que porcentaje de los casos terminados duro menos que el
  plazo objetivo y cuanto duro en promedio.

Combina los casos de Bonita con datos propios: el periodo y la gravedad son de la emergencia
local, enlazada a su caso por `bonita_case_id`. Las llamadas a Bonita las hace el backend; el
navegador nunca habla con Bonita.

Si Bonita no responde, `obtener_seccion_de_proceso` propaga el error del contrato
(`ERRORES_DEL_MOTOR`): la pantalla lo muestra en la seccion, con reintento, y el resto del panel
no se entera porque ninguna otra seccion llama a Bonita.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from app.core.errores import (
    RespuestaExternaInvalida,
    ServicioExternoNoDisponible,
    SistemaExternoRechazo,
    TiempoDeEsperaAgotado,
)
from app.core.integraciones.bonita import consultas
from app.core.integraciones.bonita.api import BONITA_PROCESO_NOMBRE
from app.core.interfaz.plantillas import etiqueta_gravedad
from app.modulos.emergencias import servicios as servicios_de_emergencias
from app.modulos.emergencias.modelos import NivelGravedad
from app.modulos.indicadores import graficos
from app.modulos.indicadores.etapas import ETAPAS, PLAZO_OBJETIVO_DIAS, Etapa, duraciones_por_tarea
from app.modulos.indicadores.exportacion import TablaExportable
from app.modulos.indicadores.periodo import Periodo
from app.modulos.indicadores.tiempos import (
    columnas_de_duracion,
    duracion_como_texto,
    duracion_entre,
    porcentaje_entero,
    promedio_de_duraciones,
)

# Lo que puede salir mal al consultar Bonita, segun el contrato de errores.
ERRORES_DEL_MOTOR = (
    ServicioExternoNoDisponible,
    TiempoDeEsperaAgotado,
    SistemaExternoRechazo,
    RespuestaExternaInvalida,
)

MENSAJE_MOTOR_NO_DISPONIBLE = "No se pudieron obtener los datos del motor de procesos."
SIN_OCURRENCIAS = "Sin ocurrencias"
SIN_CASOS = "Sin casos"

# --- Etapas del proceso -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TiempoDeEtapa:
    """El tiempo promedio de una etapa sobre los casos que pasaron por ella."""

    etapa: Etapa
    casos: int
    promedio: timedelta | None

    @property
    def promedio_como_texto(self) -> str:
        return SIN_OCURRENCIAS if self.promedio is None else duracion_como_texto(self.promedio)


@dataclass(frozen=True, slots=True)
class EtapasDelProceso:
    gravedad: NivelGravedad | None
    casos_terminados: int
    filas: tuple[TiempoDeEtapa, ...]

    def grafico(self) -> dict[str, Any]:
        return graficos.barras_de_duracion(
            [fila.etapa.etiqueta for fila in self.filas],
            [fila.promedio for fila in self.filas],
            tonos=["serie-1"] * len(self.filas),
            detalles=[
                f"{fila.casos} {'caso' if fila.casos == 1 else 'casos'}" for fila in self.filas
            ],
            horizontal=True,
            sin_dato=SIN_OCURRENCIAS,
        )

    def tabla(self) -> TablaExportable:
        """Una fila por etapa, como el grafico. Sin casos terminados queda vacia."""
        columnas = ("etapa", "casos", "tiempo_promedio_segundos", "tiempo_promedio")
        if not self.casos_terminados:
            return TablaExportable(columnas=columnas)
        return TablaExportable(
            columnas=columnas,
            filas=tuple(
                (fila.etapa.etiqueta, fila.casos, *columnas_de_duracion(fila.promedio))
                for fila in self.filas
            ),
        )

    def a_diccionario(self) -> dict[str, Any]:
        return {
            "gravedad": self.gravedad.value if self.gravedad else None,
            "casos_terminados": self.casos_terminados,
            "datos": self.tabla().como_json(),
        }


# --- Resolucion en termino ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResolucionDeGravedad:
    gravedad: NivelGravedad
    plazo_dias: int
    casos: int
    en_termino: int
    tiempo_medio: timedelta | None

    @property
    def etiqueta(self) -> str:
        return etiqueta_gravedad(self.gravedad)

    @property
    def plazo(self) -> timedelta:
        return timedelta(days=self.plazo_dias)

    @property
    def porcentaje_en_termino(self) -> int | None:
        return porcentaje_entero(self.en_termino, self.casos)

    @property
    def tiempo_medio_como_texto(self) -> str:
        return SIN_CASOS if self.tiempo_medio is None else duracion_como_texto(self.tiempo_medio)


@dataclass(frozen=True, slots=True)
class ResolucionEnTermino:
    """Por gravedad (en el orden del catalogo, como el filtro), casos en el plazo y duracion."""

    filas: tuple[ResolucionDeGravedad, ...]
    casos_abiertos: int

    @property
    def casos_terminados(self) -> int:
        return sum(fila.casos for fila in self.filas)

    def _tonos(self) -> list[str]:
        return [graficos.TONO_POR_GRAVEDAD[fila.gravedad] for fila in self.filas]

    def grafico_en_termino(self) -> dict[str, Any]:
        """Porcentaje de casos terminados dentro del plazo, por gravedad."""
        return graficos.barras(
            [fila.etiqueta for fila in self.filas],
            [fila.porcentaje_en_termino for fila in self.filas],
            tonos=self._tonos(),
            unidad=graficos.PORCIENTO,
            detalles=[
                f"{fila.en_termino} de {fila.casos} dentro del plazo de {fila.plazo_dias} días"
                if fila.casos
                else None
                for fila in self.filas
            ],
            maximo=100,
            sin_dato=SIN_CASOS,
        )

    def grafico_de_tiempo_medio(self) -> dict[str, Any]:
        """Tiempo medio de resolucion por gravedad, con la marca de su plazo objetivo.

        Va aparte del porcentaje (otra medida, otra unidad). La marca del plazo deja ver de un
        vistazo que gravedades se resuelven, en promedio, fuera de termino.
        """
        return graficos.barras_de_duracion(
            [fila.etiqueta for fila in self.filas],
            [fila.tiempo_medio for fila in self.filas],
            tonos=self._tonos(),
            detalles=[f"Plazo objetivo: {fila.plazo_dias} días" for fila in self.filas],
            sin_dato=SIN_CASOS,
            marcadores=graficos.Marcadores("Plazo objetivo", [fila.plazo for fila in self.filas]),
        )

    def tabla(self) -> TablaExportable:
        columnas = (
            "gravedad",
            "plazo_objetivo_dias",
            "casos_terminados",
            "casos_en_termino",
            "porcentaje_en_termino",
            "tiempo_medio_segundos",
            "tiempo_medio",
        )
        if not self.casos_terminados:
            return TablaExportable(columnas=columnas)
        return TablaExportable(
            columnas=columnas,
            filas=tuple(
                (
                    fila.etiqueta,
                    fila.plazo_dias,
                    fila.casos,
                    fila.en_termino,
                    fila.porcentaje_en_termino,
                    *columnas_de_duracion(fila.tiempo_medio),
                )
                for fila in self.filas
            ),
        )

    def a_diccionario(self) -> dict[str, Any]:
        return {
            "casos_terminados": self.casos_terminados,
            "casos_abiertos": self.casos_abiertos,
            "datos": self.tabla().como_json(),
        }


# --- La seccion ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SeccionDeProceso:
    etapas: EtapasDelProceso
    resolucion: ResolucionEnTermino

    def a_diccionario(self) -> dict[str, Any]:
        return {
            "filtros": {"gravedad": self.etapas.gravedad.value if self.etapas.gravedad else None},
            "etapas": self.etapas.a_diccionario(),
            "resolucion_en_termino": self.resolucion.a_diccionario(),
        }


def _etapas(
    casos: list[consultas.CasoArchivado], gravedad: NivelGravedad | None
) -> EtapasDelProceso:
    lineas = consultas.lineas_de_tiempo(casos)
    duraciones: dict[str, list[timedelta]] = defaultdict(list)
    for caso in casos:
        for nombre, duracion in duraciones_por_tarea(
            lineas[caso.caso_id], caso.iniciado_en
        ).items():
            duraciones[nombre].append(duracion)
    return EtapasDelProceso(
        gravedad=gravedad,
        casos_terminados=len(casos),
        filas=tuple(
            TiempoDeEtapa(
                etapa=etapa,
                casos=len(duraciones[etapa.nombre_en_bonita]),
                promedio=promedio_de_duraciones(duraciones[etapa.nombre_en_bonita]),
            )
            for etapa in ETAPAS
        ),
    )


def _resolucion(
    terminados: list[tuple[NivelGravedad, consultas.CasoArchivado]], casos_abiertos: int
) -> ResolucionEnTermino:
    duraciones: dict[NivelGravedad, list[timedelta]] = defaultdict(list)
    for gravedad, caso in terminados:
        duraciones[gravedad].append(duracion_entre(caso.iniciado_en, caso.finalizado_en))

    filas = []
    for gravedad in NivelGravedad:
        plazo_dias = PLAZO_OBJETIVO_DIAS[gravedad]
        plazo = timedelta(days=plazo_dias)
        de_la_gravedad = duraciones[gravedad]
        filas.append(
            ResolucionDeGravedad(
                gravedad=gravedad,
                plazo_dias=plazo_dias,
                casos=len(de_la_gravedad),
                en_termino=sum(duracion <= plazo for duracion in de_la_gravedad),
                tiempo_medio=promedio_de_duraciones(de_la_gravedad),
            )
        )
    return ResolucionEnTermino(filas=tuple(filas), casos_abiertos=casos_abiertos)


def obtener_seccion_de_proceso(
    periodo: Periodo, gravedad: NivelGravedad | None = None
) -> SeccionDeProceso:
    """Etapas y resolucion en termino de los casos de las emergencias registradas en el periodo.

    `gravedad`, si se indica, acota solo las etapas (es el filtro de ese grafico): la resolucion
    en termino ya se muestra abierta por gravedad.
    """
    desde, hasta = periodo.limites_utc()
    gravedad_por_caso = {
        registro.bonita_case_id: registro.nivel_gravedad
        for registro in servicios_de_emergencias.listar_registros_de_emergencias(
            desde=desde, hasta=hasta
        )
        if registro.bonita_case_id
    }

    foto = consultas.foto_del_proceso(BONITA_PROCESO_NOMBRE)
    terminados = [
        (gravedad_por_caso[caso_id], caso)
        for caso_id, caso in foto.casos_terminados.items()
        if caso_id in gravedad_por_caso
    ]
    abiertos = foto.casos_abiertos & gravedad_por_caso.keys()

    return SeccionDeProceso(
        etapas=_etapas(
            [caso for nivel, caso in terminados if gravedad is None or nivel == gravedad],
            gravedad,
        ),
        resolucion=_resolucion(terminados, casos_abiertos=len(abiertos)),
    )
