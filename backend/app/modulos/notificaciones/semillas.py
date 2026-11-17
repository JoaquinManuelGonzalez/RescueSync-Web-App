"""Datos semilla de notificaciones vinculadas a los flujos demo y de prueba."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria
from app.modulos.emergencias.modelos import Emergencia
from app.modulos.notificaciones.modelos import Notificacion
from app.modulos.organizaciones.modelos import Organizacion, TipoOrganizacion

TITULO_EMERGENCIA_DEMO = "Temporal severo con voladura de techos en Chascomús"
MARCA_CONVOCATORIA_DEMO = "SEED_DEMO_OFERTAS"
MARCA_CONVOCATORIA_PRUEBA = "SEED_PRUEBA_SELECCION_SIN_BONITA"
MARCA_CONVOCATORIA_COBERTURA_INSUFICIENTE = "SEED_PRUEBA_COBERTURA_INSUFICIENTE"
NOMBRE_CENTRO_COORDINADOR = "Centro Coordinador Regional Buenos Aires"


@registrar("notificaciones")
def sembrar_notificaciones() -> list[ResultadoSemilla]:
    """Crea avisos demo y de prueba para emergencias y convocatorias sembradas."""
    emergencia = Emergencia.query.filter_by(titulo=TITULO_EMERGENCIA_DEMO).first()
    convocatoria = Convocatoria.query.filter_by(observaciones=MARCA_CONVOCATORIA_DEMO).first()
    centro = Organizacion.query.filter_by(nombre=NOMBRE_CENTRO_COORDINADOR).first()
    if emergencia is None or convocatoria is None or centro is None:
        raise ValueError("No se encontraron los datos demo necesarios para notificaciones.")

    resultado = ResultadoSemilla("notificaciones")
    mensaje_emergencia = (
        f"Se registró la emergencia «{emergencia.titulo}» en {emergencia.zona_afectada}."
    )
    _, fue_creada = _obtener_o_actualizar(
        organizacion_id=centro.id,
        titulo="Nueva emergencia registrada",
        mensaje=mensaje_emergencia,
        enlace=f"/emergencias/{emergencia.id}",
    )
    resultado.contar(fue_creada)

    organizaciones_ong = db.session.execute(
        select(Organizacion).where(
            Organizacion.tipo == TipoOrganizacion.ong,
            Organizacion.activo.is_(True),
        )
    ).scalars()
    for organizacion in organizaciones_ong:
        mensaje_convocatoria = (
            f"Se abrió una convocatoria para la emergencia «{emergencia.titulo}»."
        )
        _, fue_creada = _obtener_o_actualizar(
            organizacion_id=organizacion.id,
            titulo="Nueva convocatoria disponible",
            mensaje=mensaje_convocatoria,
            enlace=f"/convocatorias/{convocatoria.id}",
        )
        resultado.contar(fue_creada)

    convocatoria_prueba = Convocatoria.query.filter_by(
        observaciones=MARCA_CONVOCATORIA_PRUEBA
    ).first()
    if convocatoria_prueba is not None:
        municipio = convocatoria_prueba.emergencia.municipio
        _, fue_creada = _obtener_o_actualizar(
            organizacion_id=municipio.id,
            titulo="PRUEBA - Ofertas listas para seleccionar",
            mensaje=(
                "Caso de prueba sin Bonita: la cobertura fue confirmada y el municipio "
                "puede seleccionar líneas de oferta."
            ),
            enlace=f"/adjudicaciones/convocatoria/{convocatoria_prueba.id}",
        )
        resultado.contar(fue_creada)

    convocatoria_cobertura = Convocatoria.query.filter_by(
        observaciones=MARCA_CONVOCATORIA_COBERTURA_INSUFICIENTE
    ).first()
    if convocatoria_cobertura is None:
        raise ValueError("Convocatoria de cobertura insuficiente no encontrada.")
    _, fue_creada = _obtener_o_actualizar(
        organizacion_id=centro.id,
        titulo="Cobertura insuficiente: decisión pendiente",
        mensaje=(
            f"La convocatoria para «{convocatoria_cobertura.emergencia.titulo}» "
            f"alcanzó el {convocatoria_cobertura.porcentaje_cobertura:.2f}% de cobertura. "
            "Revisá las ofertas y decidí si aceptar la cobertura parcial o reabrirla."
        ),
        enlace=(f"/convocatorias/{convocatoria_cobertura.id}/cobertura-insuficiente"),
    )
    resultado.contar(fue_creada)

    return [resultado]


def _obtener_o_actualizar(
    *, organizacion_id: uuid.UUID, titulo: str, mensaje: str, enlace: str
) -> tuple[Notificacion, bool]:
    """Mantiene actualizados los enlaces de los avisos demo sin duplicarlos."""
    notificacion = db.session.execute(
        select(Notificacion).where(
            Notificacion.organizacion_id == organizacion_id,
            Notificacion.titulo == titulo,
            Notificacion.mensaje == mensaje,
        )
    ).scalar_one_or_none()
    if notificacion is not None:
        notificacion.enlace = enlace
        return notificacion, False
    return obtener_o_crear(
        Notificacion,
        claves={
            "organizacion_id": organizacion_id,
            "titulo": titulo,
            "enlace": enlace,
        },
        valores={"mensaje": mensaje},
    )
