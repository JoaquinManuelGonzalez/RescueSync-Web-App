"""Datos semilla de notificaciones vinculadas al flujo demo."""

from __future__ import annotations

from sqlalchemy import select

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria
from app.modulos.emergencias.modelos import Emergencia
from app.modulos.notificaciones.modelos import Notificacion
from app.modulos.organizaciones.modelos import Organizacion, TipoOrganizacion

TITULO_EMERGENCIA_DEMO = "Temporal severo con voladura de techos en Chascomús"
MARCA_CONVOCATORIA_DEMO = "SEED_DEMO_OFERTAS"
NOMBRE_CENTRO_COORDINADOR = "Centro Coordinador Regional Buenos Aires"


@registrar("notificaciones")
def sembrar_notificaciones() -> list[ResultadoSemilla]:
    """Crea avisos demo para la emergencia y convocatoria sembradas."""
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
            enlace=f"/ofertas?convocatoria_id={convocatoria.id}",
        )
        resultado.contar(fue_creada)

    return [resultado]


def _obtener_o_actualizar(
    *, organizacion_id: int, titulo: str, mensaje: str, enlace: str
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
