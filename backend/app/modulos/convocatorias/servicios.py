"""Servicios de negocio para la apertura de convocatorias."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.errores import (
    ConflictoDeEstado,
    RecursoNoEncontrado,
    ReglaDeNegocioIncumplida,
    SolicitudInvalida,
)
from app.core.logging import registrar_evento
from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria, EstadoConvocatoria
from app.modulos.emergencias.modelos import (
    Emergencia,
    EstadoEmergencia,
    EstadoLote,
    LoteNecesidad,
)
from app.modulos.usuarios_roles.modelos import Usuario


def _validar_resumen(resumen_situacion: str | None) -> str:
    """Valida y normaliza el resumen requerido para publicar la convocatoria."""
    if not isinstance(resumen_situacion, str) or not resumen_situacion.strip():
        raise SolicitudInvalida(
            "El resumen de situación es obligatorio.",
            detalle={"campo": "resumen_situacion"},
        )
    return resumen_situacion.strip()


def _normalizar_fecha(fecha: datetime | None) -> datetime:
    """Valida el vencimiento y lo devuelve en UTC; las fechas sin zona se interpretan como UTC."""
    if not isinstance(fecha, datetime):
        raise SolicitudInvalida(
            "La fecha límite para presentar ofertas es obligatoria.",
            detalle={"campo": "fecha_cierre"},
        )

    if fecha.tzinfo is None:
        return fecha.replace(tzinfo=UTC)
    return fecha.astimezone(UTC)


def cerrar_convocatorias_vencidas(*, emergencia_id: int | None = None) -> int:
    """Cierra convocatorias vencidas y devuelve sus emergencias a evaluación."""
    ahora = datetime.now(UTC)
    consulta = select(Convocatoria).where(
        Convocatoria.estado == EstadoConvocatoria.abierta,
        Convocatoria.fecha_cierre <= ahora,
    )
    if emergencia_id is not None:
        consulta = consulta.where(Convocatoria.emergencia_id == emergencia_id)
    vencidas = db.session.execute(consulta.with_for_update()).scalars().all()
    if not vencidas:
        return 0

    emergencias_afectadas = set()
    for convocatoria in vencidas:
        convocatoria.estado = EstadoConvocatoria.cerrada
        emergencias_afectadas.add(convocatoria.emergencia_id)

    for id_emergencia in emergencias_afectadas:
        sigue_abierta = db.session.execute(
            select(Convocatoria.id).where(
                Convocatoria.emergencia_id == id_emergencia,
                Convocatoria.estado == EstadoConvocatoria.abierta,
                Convocatoria.fecha_cierre > ahora,
            )
        ).scalar_one_or_none()
        if sigue_abierta is None:
            emergencia = db.session.execute(
                select(Emergencia)
                .where(Emergencia.id == id_emergencia)
                .with_for_update()
            ).scalar_one_or_none()
            if emergencia and emergencia.estado == EstadoEmergencia.activa:
                emergencia.estado = EstadoEmergencia.registrada

    db.session.commit()
    return len(vencidas)


def cerrar_convocatoria(convocatoria_id: int) -> Convocatoria:
    """Cierra la recepción de ofertas y habilita una nueva evaluación de necesidades."""
    convocatoria = db.session.execute(
        select(Convocatoria)
        .where(Convocatoria.id == convocatoria_id)
        .with_for_update()
    ).scalar_one_or_none()
    if convocatoria is None:
        raise RecursoNoEncontrado(f"Convocatoria con id {convocatoria_id} no encontrada.")
    if convocatoria.estado == EstadoConvocatoria.cerrada:
        return convocatoria
    if convocatoria.estado != EstadoConvocatoria.abierta:
        raise ConflictoDeEstado(
            "Solo se puede cerrar una convocatoria que esté abierta.",
            detalle={"convocatoria_id": convocatoria.id, "estado": convocatoria.estado.value},
        )

    convocatoria.estado = EstadoConvocatoria.cerrada
    sigue_abierta = db.session.execute(
        select(Convocatoria.id).where(
            Convocatoria.emergencia_id == convocatoria.emergencia_id,
            Convocatoria.id != convocatoria.id,
            Convocatoria.estado == EstadoConvocatoria.abierta,
            Convocatoria.fecha_cierre > datetime.now(UTC),
        )
    ).scalar_one_or_none()
    if sigue_abierta is None:
        emergencia = db.session.execute(
            select(Emergencia)
            .where(Emergencia.id == convocatoria.emergencia_id)
            .with_for_update()
        ).scalar_one_or_none()
        if emergencia and emergencia.estado == EstadoEmergencia.activa:
            emergencia.estado = EstadoEmergencia.registrada

    db.session.commit()
    registrar_evento(
        logging.INFO,
        "convocatoria_cerrada",
        convocatoria_id=convocatoria.id,
        emergencia_id=convocatoria.emergencia_id,
    )
    return convocatoria


def crear_convocatoria(
    *,
    emergencia_id: int,
    coordinador_id: int,
    resumen_situacion: str,
    fecha_cierre: datetime,
    observaciones: str | None = None,
) -> Convocatoria:
    """Publica una convocatoria para los lotes pendientes de una emergencia en revisión."""
    if not emergencia_id:
        raise SolicitudInvalida(
            "La emergencia es obligatoria.",
            detalle={"campo": "emergencia_id"},
        )
    if not coordinador_id:
        raise SolicitudInvalida(
            "El usuario coordinador es obligatorio.",
            detalle={"campo": "coordinador_id"},
        )

    cerrar_convocatorias_vencidas(emergencia_id=emergencia_id)

    resumen = _validar_resumen(resumen_situacion)
    cierre = _normalizar_fecha(fecha_cierre)
    inicio = datetime.now(UTC)
    if cierre <= inicio:
        raise SolicitudInvalida(
            "La fecha límite debe ser posterior al momento de publicación.",
            detalle={"campo": "fecha_cierre"},
        )

    emergencia = db.session.execute(
        select(Emergencia)
        .where(Emergencia.id == emergencia_id)
        .with_for_update()
    ).scalar_one_or_none()
    if emergencia is None:
        raise RecursoNoEncontrado(f"Emergencia con id {emergencia_id} no encontrada.")
    if emergencia.estado != EstadoEmergencia.en_evaluacion:
        raise ReglaDeNegocioIncumplida(
            "La emergencia debe estar en revisión antes de abrir la convocatoria.",
            detalle={"emergencia_id": emergencia.id, "estado": emergencia.estado.value},
        )

    coordinador = db.session.get(Usuario, coordinador_id)
    if coordinador is None:
        raise RecursoNoEncontrado(f"Usuario coordinador con id {coordinador_id} no encontrado.")

    convocatoria_abierta = db.session.execute(
        select(Convocatoria.id)
        .where(
            Convocatoria.emergencia_id == emergencia.id,
            Convocatoria.estado == EstadoConvocatoria.abierta,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if convocatoria_abierta is not None:
        raise ConflictoDeEstado(
            "Ya existe una convocatoria abierta para esta emergencia.",
            detalle={"emergencia_id": emergencia.id, "estado": EstadoConvocatoria.abierta.value},
        )

    lotes_existentes = db.session.execute(
        select(LoteNecesidad)
        .where(LoteNecesidad.emergencia_id == emergencia.id)
        .order_by(LoteNecesidad.id)
        .with_for_update()
    ).scalars().all()
    if not lotes_existentes:
        raise SolicitudInvalida(
            "La emergencia debe tener al menos un lote de necesidad para publicar.",
            detalle={"campo": "lotes"},
        )
    lotes = [lote for lote in lotes_existentes if lote.estado == EstadoLote.pendiente]
    if not lotes:
        raise ConflictoDeEstado(
            "Agregá necesidades nuevas antes de abrir otra convocatoria.",
            detalle={"emergencia_id": emergencia.id, "campo": "lotes"},
        )

    convocatoria = Convocatoria(
        emergencia_id=emergencia.id,
        coordinador_id=coordinador.id,
        fecha_inicio=inicio,
        fecha_cierre=cierre,
        resumen_situacion=resumen,
        observaciones=observaciones.strip() if observaciones and observaciones.strip() else None,
        estado=EstadoConvocatoria.abierta,
    )
    emergencia.estado = EstadoEmergencia.activa
    db.session.add(convocatoria)
    db.session.flush()
    for lote in lotes:
        lote.convocatoria = convocatoria
        lote.estado = EstadoLote.en_convocatoria

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    registrar_evento(
        logging.INFO,
        "convocatoria_publicada",
        convocatoria_id=convocatoria.id,
        emergencia_id=emergencia.id,
        coordinador_id=coordinador.id,
        lotes=len(lotes),
    )
    return convocatoria