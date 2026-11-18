"""Datos semilla de ejecucion: lo que hizo cada ONG con lo que se le adjudico en las emergencias
historicas (ofertas/semillas.py::ADJUDICACIONES_HISTORICAS).

Con ellas el ranking de ONGs del panel de auditoria tiene tiempos de ejecucion que mostrar: hay
ONGs con varias actividades finalizadas, una con actividades en curso y una sin ninguna
finalizada (que el ranking muestra con "—").
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria
from app.modulos.ejecucion_cierre.modelos import EstadoTareaEjecucion, TareaEjecucion
from app.modulos.emergencias.modelos import Emergencia
from app.modulos.ofertas.modelos import EstadoOferta, Oferta, OfertaLinea
from app.modulos.ofertas.semillas import MARCA_CONVOCATORIA_HISTORICA
from app.modulos.organizaciones.modelos import Organizacion

# (emergencia, ONG, dias desde la adjudicacion hasta finalizar; None = todavia en curso).
EJECUCIONES_HISTORICAS: tuple[tuple[str, str, float | None], ...] = (
    ("Granizo sobre la zona hortícola de La Plata", "Cruz Solidaria", 9),
    ("Granizo sobre la zona hortícola de La Plata", "Bomberos Voluntarios de La Plata", 6),
    ("Granizo sobre la zona hortícola de La Plata", "Manos Unidas", 7.5),
    ("Desborde de la laguna de Chascomús", "Manos Unidas", 12),
    ("Incendio de pastizales en el periurbano de La Plata", "Cruz Solidaria", 4),
    ("Incendio de pastizales en el periurbano de La Plata", "Bomberos Voluntarios de La Plata", 5),
    (
        "Incendio de pastizales en el periurbano de La Plata",
        "Cruz Roja Argentina - Filial Bahía Blanca",
        3,
    ),
    ("Temporal de viento y lluvia en Pergamino", "Manos Unidas", 2.5),
    ("Temporal de viento y lluvia en Pergamino", "Cruz Roja Argentina - Filial Bahía Blanca", None),
    ("Temporal de viento y lluvia en Pergamino", "Grupo Scouts de Pergamino", None),
)


def _oferta_adjudicada(convocatoria_id: uuid.UUID, organizacion_id: uuid.UUID) -> Oferta:
    """La oferta adjudicada de la convocatoria en la que la ONG tiene lineas seleccionadas."""
    oferta = db.session.execute(
        select(Oferta)
        .join(OfertaLinea, OfertaLinea.oferta_id == Oferta.id)
        .where(
            Oferta.convocatoria_id == convocatoria_id,
            Oferta.estado == EstadoOferta.adjudicada,
            OfertaLinea.organizacion_id == organizacion_id,
            OfertaLinea.seleccionada.is_(True),
        )
        .limit(1)
    ).scalar_one_or_none()
    if oferta is None:
        raise ValueError(
            f"La organizacion {organizacion_id} no tiene lineas adjudicadas en la convocatoria "
            f"{convocatoria_id}. Revisar ofertas/semillas.py::ADJUDICACIONES_HISTORICAS."
        )
    return oferta


@registrar("ejecuciones_historicas")
def sembrar_ejecuciones_historicas() -> list[ResultadoSemilla]:
    """Una tarea de ejecucion por ONG adjudicada en cada emergencia historica.

    Como las adjudicaciones historicas, se reescriben en cada corrida (estado y fechas).
    """
    resultado = ResultadoSemilla("tareas_de_ejecucion")
    for titulo, nombre_ong, dias in EJECUCIONES_HISTORICAS:
        emergencia = db.session.execute(select(Emergencia).filter_by(titulo=titulo)).scalar_one()
        organizacion = db.session.execute(
            select(Organizacion).filter_by(nombre=nombre_ong)
        ).scalar_one()
        convocatoria = db.session.execute(
            select(Convocatoria).filter_by(
                emergencia_id=emergencia.id, observaciones=MARCA_CONVOCATORIA_HISTORICA
            )
        ).scalar_one()
        oferta = _oferta_adjudicada(convocatoria.id, organizacion.id)

        tarea, creada = obtener_o_crear(
            TareaEjecucion,
            claves={"oferta_id": oferta.id, "organizacion_id": organizacion.id},
            valores={"emergencia_id": emergencia.id},
        )
        tarea.emergencia_id = emergencia.id
        tarea.fecha_inicio = convocatoria.adjudicada_en
        if dias is None:
            tarea.estado = EstadoTareaEjecucion.en_progreso
            tarea.fecha_fin = None
        else:
            tarea.estado = EstadoTareaEjecucion.finalizada
            tarea.fecha_fin = convocatoria.adjudicada_en + timedelta(days=dias)
        resultado.contar(creada)
    return [resultado]
