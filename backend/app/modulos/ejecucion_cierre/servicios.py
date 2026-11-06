"""Servicios del módulo de ejecución y cierre de RescueSync.

Gestiona el ciclo de vida de las tareas de campo asignadas a las ONGs,
su seguimiento y la notificación a Bonita para la liberación de recursos.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.errores import ConflictoDeEstado, RecursoNoEncontrado
from app.core.integraciones.bonita.proceso import finalizar_actividad_ong
from app.core.logging import registrar_evento
from app.extensiones import db
from app.modulos.ejecucion_cierre.modelos import EstadoTareaEjecucion, TareaEjecucion
from app.modulos.emergencias.modelos import Emergencia
from app.modulos.ofertas.modelos import EstadoOferta, Oferta, OfertaOrganizacion
from app.modulos.organizaciones.modelos import Organizacion

logger = logging.getLogger(__name__)


def sincronizar_tareas_para_ong(organizacion_id: int) -> list[TareaEjecucion]:
    """Garantiza que existan tareas de ejecución para todas las ofertas adjudicadas a la ONG."""
    # 1. Buscar todas las ofertas en estado adjudicada donde la ONG participa
    # ya sea como líder, miembro del consorcio o aportante directo.
    consulta_ofertas = (
        select(Oferta)
        .outerjoin(OfertaOrganizacion, OfertaOrganizacion.oferta_id == Oferta.id)
        .where(
            Oferta.estado == EstadoOferta.adjudicada,
            db.or_(
                OfertaOrganizacion.organizacion_id == organizacion_id,
                Oferta.usuario.has(organizacion_id=organizacion_id),
            ),
        )
        .distinct()
    )
    ofertas_adjudicadas = db.session.scalars(consulta_ofertas).all()

    # 2. Para cada oferta adjudicada, verificar si ya tiene TareaEjecucion para esta ONG
    hubo_creacion = False
    for oferta in ofertas_adjudicadas:
        tarea_existente = db.session.scalar(
            select(TareaEjecucion).where(
                TareaEjecucion.oferta_id == oferta.id,
                TareaEjecucion.organizacion_id == organizacion_id,
            )
        )
        if not tarea_existente:
            emergencia_id = oferta.convocatoria.emergencia_id if oferta.convocatoria else None
            if not emergencia_id:
                continue

            nueva_tarea = TareaEjecucion(
                emergencia_id=emergencia_id,
                oferta_id=oferta.id,
                organizacion_id=organizacion_id,
                estado=EstadoTareaEjecucion.en_progreso,
            )
            db.session.add(nueva_tarea)
            hubo_creacion = True

    if hubo_creacion:
        db.session.commit()

    # 3. Retornar todas las tareas de la ONG ordenadas cronológicamente
    consulta_tareas = (
        select(TareaEjecucion)
        .where(TareaEjecucion.organizacion_id == organizacion_id)
        .order_by(TareaEjecucion.fecha_inicio.desc())
    )
    return list(db.session.scalars(consulta_tareas).all())


def obtener_tarea_ong(tarea_id: int, organizacion_id: int) -> TareaEjecucion:
    """Devuelve la tarea si existe y pertenece a la organización solicitante."""
    tarea = db.session.get(TareaEjecucion, tarea_id)
    if not tarea or tarea.organizacion_id != organizacion_id:
        raise RecursoNoEncontrado("La tarea solicitada no existe o no pertenece a tu organización.")
    return tarea


def finalizar_tarea_ong(
    tarea_id: int,
    organizacion_id: int,
    usuario_id: int,
    username: str,
    observaciones: str | None = None,
) -> TareaEjecucion:
    """Solicita el cierre y finaliza localmente solo si Bonita lo confirma."""
    tarea = obtener_tarea_ong(tarea_id, organizacion_id)

    if tarea.estado != EstadoTareaEjecucion.en_progreso:
        raise ConflictoDeEstado("La tarea no se encuentra en curso para ser finalizada.")

    tarea.estado = EstadoTareaEjecucion.cierre_pendiente
    tarea.usuario_id = usuario_id
    tarea.observaciones = observaciones.strip() if observaciones else None
    db.session.commit()

    registrar_evento(
        logging.INFO,
        "tarea_ejecucion_cierre_solicitado",
        "La ONG solicitó finalizar una tarea de ejecución",
        tarea_id=tarea.id,
        emergencia_id=tarea.emergencia_id,
        oferta_id=tarea.oferta_id,
        organizacion_id=organizacion_id,
    )

    emergencia = db.session.get(Emergencia, tarea.emergencia_id)
    organizacion = db.session.get(Organizacion, organizacion_id)
    identificador_nacional = (
        organizacion.identificador_nacional if organizacion else str(organizacion_id)
    )

    if emergencia and emergencia.bonita_case_id:
        try:
            finalizar_actividad_ong(
                username=username,
                case_id=emergencia.bonita_case_id,
                identificador_ong=identificador_nacional,
                observaciones=tarea.observaciones,
            )
            tarea.estado = EstadoTareaEjecucion.finalizada
            tarea.fecha_fin = datetime.now(UTC)
            db.session.commit()
            registrar_evento(
                logging.INFO,
                "tarea_ejecucion_finalizada",
                "Bonita confirmó la finalización de la tarea",
                tarea_id=tarea.id,
                case_id=emergencia.bonita_case_id,
                identificador_ong=identificador_nacional,
            )
        except Exception as error:  # noqa: BLE001
            db.session.rollback()
            logger.warning(
                "No se pudo confirmar el cierre en Bonita para el caso %s: %s",
                emergencia.bonita_case_id,
                error,
            )
            registrar_evento(
                logging.WARN,
                "bonita_finalizacion_fallida",
                "La tarea permanece pendiente de confirmación",
                tarea_id=tarea.id,
                case_id=emergencia.bonita_case_id,
                error=str(error),
            )
            tarea = db.session.get(TareaEjecucion, tarea_id)
    else:
        registrar_evento(
            logging.WARN,
            "tarea_ejecucion_sin_caso_bonita",
            "La tarea permanece pendiente porque no tiene un caso de proceso asociado",
            tarea_id=tarea.id,
            emergencia_id=tarea.emergencia_id,
        )

    return tarea
