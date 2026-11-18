"""Servicios del módulo de ejecución y cierre de RescueSync.

Gestiona el ciclo de vida local de las tareas de campo asignadas a las ONGs.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, and_, exists, select
from sqlalchemy.orm import selectinload

from app.core.errores import ConflictoDeEstado, ErrorDeAplicacion, RecursoNoEncontrado
from app.core.integraciones.bonita.proceso import error_sin_guardar, finalizar_actividad_ong
from app.core.integraciones.bonita.sesion import BONITA_USER
from app.core.logging import registrar_evento
from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria
from app.modulos.ejecucion_cierre.modelos import EstadoTareaEjecucion, TareaEjecucion
from app.modulos.emergencias.modelos import Emergencia, EstadoEmergencia, LoteItem
from app.modulos.ofertas.modelos import (
    EstadoOferta,
    Oferta,
    OfertaLinea,
    OfertaOrganizacion,
)

logger = logging.getLogger(__name__)


def sincronizar_tareas_para_ong(organizacion_id: uuid.UUID) -> list[TareaEjecucion]:
    """Crea tareas para líneas adjudicadas que pertenecen a la ONG y fueron aceptadas."""
    # La asociación de consorcio es la fuente de verdad de quién participa y si aceptó.
    consulta_ofertas = (
        select(Oferta)
        .join(OfertaOrganizacion, OfertaOrganizacion.oferta_id == Oferta.id)
        .where(
            Oferta.estado == EstadoOferta.adjudicada,
            OfertaOrganizacion.organizacion_id == organizacion_id,
            OfertaOrganizacion.estado_participacion == "aceptada",
            exists(
                select(OfertaLinea.id).where(
                    OfertaLinea.oferta_id == Oferta.id,
                    OfertaLinea.organizacion_id == organizacion_id,
                    OfertaLinea.seleccionada.is_(True),
                )
            ),
        )
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
        .join(OfertaLinea, OfertaLinea.oferta_id == TareaEjecucion.oferta_id)
        .where(TareaEjecucion.organizacion_id == organizacion_id)
        .where(
            OfertaLinea.organizacion_id == organizacion_id,
            OfertaLinea.seleccionada.is_(True),
        )
        .options(
            selectinload(TareaEjecucion.oferta)
            .selectinload(Oferta.items)
            .selectinload(OfertaLinea.lote_item)
            .selectinload(LoteItem.item)
        )
        .order_by(TareaEjecucion.fecha_inicio.desc())
    )
    return list(db.session.scalars(consulta_tareas).unique().all())


def obtener_tarea_ong(tarea_id: uuid.UUID, organizacion_id: uuid.UUID) -> TareaEjecucion:
    """Devuelve la tarea si existe y pertenece a la organización solicitante."""
    tarea = (
        db.session.scalars(
            select(TareaEjecucion)
            .join(OfertaLinea, OfertaLinea.oferta_id == TareaEjecucion.oferta_id)
            .where(
                TareaEjecucion.id == tarea_id,
                TareaEjecucion.organizacion_id == organizacion_id,
                OfertaLinea.organizacion_id == organizacion_id,
                OfertaLinea.seleccionada.is_(True),
            )
        )
        .unique()
        .first()
    )
    if not tarea:
        raise RecursoNoEncontrado("La tarea solicitada no existe o no pertenece a tu organización.")
    return tarea


def finalizar_tarea_ong(
    tarea_id: uuid.UUID,
    organizacion_id: uuid.UUID,
    usuario_id: uuid.UUID,
    observaciones: str | None = None,
) -> TareaEjecucion:
    """Registra que la ONG completó una actividad adjudicada.

    Si con esta terminan todas las ONG de la emergencia, completa la tarea de Bonita y deja la
    emergencia finalizada en la misma transacción: si el motor no recibe la finalización, no se
    guarda nada y la ONG puede reintentar (ver `_comunicar_finalizacion_a_bonita`).
    """
    sincronizar_tareas_para_ong(organizacion_id)
    tarea = obtener_tarea_ong(tarea_id, organizacion_id)

    if tarea.estado not in (
        EstadoTareaEjecucion.en_progreso,
        EstadoTareaEjecucion.cierre_pendiente,
    ):
        raise ConflictoDeEstado("La tarea no se encuentra en curso para ser finalizada.")

    tarea.estado = EstadoTareaEjecucion.finalizada
    tarea.fecha_fin = datetime.now(UTC)
    tarea.usuario_id = usuario_id
    tarea.observaciones = observaciones.strip() if observaciones else None
    db.session.flush()

    if obtener_estado_finalizacion_emergencia(tarea.emergencia_id)["todas_finalizadas"]:
        _comunicar_finalizacion_a_bonita(tarea.emergencia)
        tarea.emergencia.estado = EstadoEmergencia.finalizada

    db.session.commit()
    registrar_evento(
        logging.INFO,
        "actividad_ong_finalizada",
        "La ONG registró localmente la finalización de una actividad",
        tarea_id=tarea.id,
        emergencia_id=tarea.emergencia_id,
        oferta_id=tarea.oferta_id,
        organizacion_id=organizacion_id,
    )
    return tarea


def _comunicar_finalizacion_a_bonita(emergencia: Emergencia) -> None:
    """Completa en Bonita la tarea "Esperar finalizacion de tareas" de la emergencia.

    Se llama antes del commit a proposito: si Bonita no la recibe, la ultima actividad no queda
    finalizada y la ONG conserva el boton para reintentar. Guardarla igual dejaria la emergencia
    activa para siempre, sin nadie que pueda volver a avisarle al motor.

    Una emergencia sin caso en Bonita (el motor estaba caido cuando se creo) no tiene ninguna
    tarea que completar: se deja constancia en el log y la emergencia finaliza en la web.
    """
    if not emergencia.bonita_case_id:
        registrar_evento(
            logging.WARNING,
            "bonita_finalizacion_sin_caso",
            emergencia_id=emergencia.id,
        )
        return

    emergencia_id, case_id = emergencia.id, emergencia.bonita_case_id
    try:
        finalizar_actividad_ong(
            username=BONITA_USER,
            case_id=case_id,
            ofertas_finalizadas_input=json.dumps({"todas_finalizadas": True}),
        )
    except ErrorDeAplicacion as error:
        db.session.rollback()
        registrar_evento(
            logging.WARNING,
            "bonita_finalizacion_no_comunicada",
            emergencia_id=emergencia_id,
            bonita_case_id=case_id,
            codigo=error.codigo,
        )
        raise error_sin_guardar(
            error, "la finalización", "La actividad sigue en ejecución."
        ) from error


def obtener_estado_finalizacion_emergencia(emergencia_id: uuid.UUID) -> dict[str, int | bool]:
    """Indica si todas las ONGs con líneas adjudicadas finalizaron sus actividades."""
    filas = db.session.execute(
        select(
            OfertaOrganizacion.organizacion_id,
            Oferta.id,
            TareaEjecucion.estado,
        )
        .join(Oferta, Oferta.id == OfertaOrganizacion.oferta_id)
        .join(Convocatoria, Convocatoria.id == Oferta.convocatoria_id)
        .join(
            OfertaLinea,
            and_(
                OfertaLinea.oferta_id == Oferta.id,
                OfertaLinea.organizacion_id == OfertaOrganizacion.organizacion_id,
                OfertaLinea.seleccionada.is_(True),
            ),
        )
        .outerjoin(
            TareaEjecucion,
            and_(
                TareaEjecucion.oferta_id == Oferta.id,
                TareaEjecucion.organizacion_id == OfertaOrganizacion.organizacion_id,
                TareaEjecucion.emergencia_id == emergencia_id,
            ),
        )
        .where(
            Convocatoria.emergencia_id == emergencia_id,
            Oferta.estado == EstadoOferta.adjudicada,
            OfertaOrganizacion.estado_participacion == "aceptada",
        )
    ).all()

    actividades_por_ong: dict[uuid.UUID, list[EstadoTareaEjecucion | None]] = {}
    for organizacion_id, _oferta_id, estado in filas:
        actividades_por_ong.setdefault(organizacion_id, []).append(estado)

    organizaciones_finalizadas = sum(
        all(estado == EstadoTareaEjecucion.finalizada for estado in estados)
        for estados in actividades_por_ong.values()
    )
    organizaciones_participantes = len(actividades_por_ong)
    return {
        "organizaciones_participantes": organizaciones_participantes,
        "organizaciones_finalizadas": organizaciones_finalizadas,
        "todas_finalizadas": (
            organizaciones_participantes > 0
            and organizaciones_finalizadas == organizaciones_participantes
        ),
    }


# --- Lectura agregada (panel de auditoria) ---------------------------------------


@dataclass(frozen=True, slots=True)
class FinalizacionDeActividad:
    """Cuando una ONG marco como finalizada su actividad en una oferta adjudicada."""

    oferta_id: uuid.UUID
    organizacion_id: uuid.UUID
    fecha_fin: datetime


def listar_finalizaciones(
    *, emergencia_ids: Select[tuple[uuid.UUID]]
) -> list[FinalizacionDeActividad]:
    """Las actividades finalizadas en esas emergencias, en una sola consulta.

    Una actividad que la ONG nunca abrio no tiene tarea, y una abierta sin terminar no tiene
    fecha de fin: ninguna de las dos aparece.
    """
    filas = db.session.execute(
        select(TareaEjecucion.oferta_id, TareaEjecucion.organizacion_id, TareaEjecucion.fecha_fin)
        .where(
            TareaEjecucion.emergencia_id.in_(emergencia_ids),
            TareaEjecucion.estado == EstadoTareaEjecucion.finalizada,
            TareaEjecucion.fecha_fin.is_not(None),
        )
        .order_by(TareaEjecucion.id)
    ).all()
    return [FinalizacionDeActividad(*fila) for fila in filas]
