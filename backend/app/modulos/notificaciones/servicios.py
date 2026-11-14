"""Casos de uso de notificaciones."""

from __future__ import annotations

from sqlalchemy import select

from app.core.errores import RecursoNoEncontrado, ReglaDeNegocioIncumplida
from app.extensiones import db
from app.modulos.notificaciones.modelos import Notificacion
from app.modulos.organizaciones.modelos import Organizacion, TipoOrganizacion

ETIQUETA_POR_ESTADO_DE_EMERGENCIA = {
    "registrada": "Registrada",
    "en_evaluacion": "En revisión",
    "activa": "Activa",
    "finalizada": "Finalizada",
    "cancelada": "Cancelada",
}


def notificar_cambio_estado_emergencia(emergencia, estado_anterior) -> Notificacion:
    """Avisa al municipio que registró una emergencia sobre su nuevo estado."""
    anterior = ETIQUETA_POR_ESTADO_DE_EMERGENCIA.get(estado_anterior.value, estado_anterior.value)
    actual = ETIQUETA_POR_ESTADO_DE_EMERGENCIA.get(emergencia.estado.value, emergencia.estado.value)
    return crear(
        organizacion_id=emergencia.municipio_id,
        titulo="Estado de emergencia actualizado",
        mensaje=(f"La emergencia «{emergencia.titulo}» cambió de estado: {anterior} → {actual}."),
        enlace=f"/emergencias/{emergencia.id}",
    )


def crear(*, organizacion_id: int, titulo: str, mensaje: str, enlace: str) -> Notificacion:
    """Crea un aviso compartido por todos los usuarios de una organización."""
    notificacion = Notificacion(
        organizacion_id=organizacion_id,
        titulo=titulo,
        mensaje=mensaje,
        enlace=enlace,
    )
    db.session.add(notificacion)
    return notificacion


def crear_para_tipo_organizacion(
    *, tipo: TipoOrganizacion, titulo: str, mensaje: str, enlace: str
) -> list[Notificacion]:
    """Crea un aviso por cada organización activa del tipo indicado."""
    organizaciones = db.session.execute(
        select(Organizacion).where(Organizacion.tipo == tipo, Organizacion.activo.is_(True))
    ).scalars()
    notificaciones = [
        crear(organizacion_id=organizacion.id, titulo=titulo, mensaje=mensaje, enlace=enlace)
        for organizacion in organizaciones
    ]
    return notificaciones


def notificar_convocatoria(convocatoria) -> list[Notificacion]:
    """Notifica una convocatoria publicada a cada ONG activa, una sola vez por ONG."""
    return crear_para_tipo_organizacion(
        tipo=TipoOrganizacion.ong,
        titulo="Nueva convocatoria disponible",
        mensaje=(
            f"Se abrió una convocatoria para la emergencia «{convocatoria.emergencia.titulo}»."
        ),
        enlace=f"/convocatorias/{convocatoria.id}",
    )


def notificar_cierre_convocatoria(convocatoria) -> list[Notificacion]:
    """Avisa el cierre al municipio, a las ONG y al centro coordinador."""
    enlace = f"/convocatorias/{convocatoria.id}"
    mensaje = (
        f"Terminó el período de la convocatoria para la emergencia "
        f"«{convocatoria.emergencia.titulo}». Estado final: "
        f"{convocatoria.estado.value.capitalize()}."
    )
    notificaciones: list[Notificacion] = []
    organizaciones_notificadas: set[int] = set()

    destinatarios = []
    if convocatoria.emergencia.municipio_id:
        destinatarios.append(convocatoria.emergencia.municipio_id)
    if convocatoria.coordinador.organizacion_id:
        destinatarios.append(convocatoria.coordinador.organizacion_id)
    destinatarios.extend(
        organizacion.id
        for organizacion in db.session.execute(
            select(Organizacion).where(
                Organizacion.tipo == TipoOrganizacion.ong,
                Organizacion.activo.is_(True),
            )
        ).scalars()
    )

    for organizacion_id in destinatarios:
        if organizacion_id in organizaciones_notificadas:
            continue
        organizaciones_notificadas.add(organizacion_id)
        notificaciones.append(
            crear(
                organizacion_id=organizacion_id,
                titulo="Convocatoria cerrada",
                mensaje=mensaje,
                enlace=enlace,
            )
        )
    return notificaciones


def notificar_cobertura_completa(convocatoria) -> Notificacion:
    """Avisa al municipio que ya puede seleccionar las ofertas evaluadas."""
    return crear(
        organizacion_id=convocatoria.emergencia.municipio_id,
        titulo="Ofertas listas para seleccionar",
        mensaje=(
            f"La cobertura de la emergencia «{convocatoria.emergencia.titulo}» fue confirmada. "
            "Ya podés seleccionar las ofertas de ayuda."
        ),
        enlace=f"/adjudicaciones/convocatoria/{convocatoria.id}",
    )


def notificar_cobertura_insuficiente(convocatoria) -> Notificacion:
    """Avisa al centro coordinador que debe resolver una cobertura incompleta."""
    organizacion_id = convocatoria.coordinador.organizacion_id
    if organizacion_id is None:
        raise ReglaDeNegocioIncumplida(
            "El coordinador de la convocatoria no tiene una organización asociada.",
            codigo="COORDINADOR_SIN_ORGANIZACION",
        )
    return crear(
        organizacion_id=organizacion_id,
        titulo="Cobertura insuficiente: decisión pendiente",
        mensaje=(
            f"La cobertura de la emergencia «{convocatoria.emergencia.titulo}» es de "
            f"{convocatoria.porcentaje_cobertura}%. Revisá las ofertas y elegí cómo continuar."
        ),
        enlace=f"/convocatorias/{convocatoria.id}/cobertura-insuficiente",
    )


def notificar_cobertura_parcial_aceptada(convocatoria) -> Notificacion:
    """Avisa al municipio que puede seleccionar ofertas con cobertura parcial."""
    return crear(
        organizacion_id=convocatoria.emergencia.municipio_id,
        titulo="Cobertura parcial aprobada: ofertas listas para seleccionar",
        mensaje=(
            f"El coordinador aceptó una cobertura del {convocatoria.porcentaje_cobertura}% "
            f"para la emergencia «{convocatoria.emergencia.titulo}». Ya podés seleccionar "
            "las ofertas de ayuda."
        ),
        enlace=f"/adjudicaciones/convocatoria/{convocatoria.id}",
    )


def notificar_resultado_adjudicacion(oferta, adjudicada: bool) -> list[Notificacion]:
    """Avisa a las organizaciones participantes el resultado de su oferta."""
    titulo = "Oferta adjudicada" if adjudicada else "Oferta no adjudicada"
    mensaje = (
        f"La oferta para la emergencia «{oferta.convocatoria.emergencia.titulo}» "
        f"fue {'adjudicada' if adjudicada else 'seleccionada por otro oferente'} "
        "por el municipio."
    )
    organizaciones = {
        miembro.organizacion_id
        for miembro in oferta.organizaciones_consorcio
        if miembro.organizacion_id is not None
    }
    return [
        crear(
            organizacion_id=organizacion_id,
            titulo=titulo,
            mensaje=mensaje,
            enlace=f"/ofertas/{oferta.id}",
        )
        for organizacion_id in organizaciones
    ]


def listar_para_usuario(usuario_id: int, *, limite: int | None = None) -> list[Notificacion]:
    """Lista avisos de la organización del usuario, del más reciente al más antiguo."""
    from app.modulos.usuarios_roles.modelos import Usuario

    organizacion_id = db.session.scalar(
        select(Usuario.organizacion_id).where(Usuario.id == usuario_id)
    )
    if organizacion_id is None:
        return []
    consulta = (
        select(Notificacion)
        .where(Notificacion.organizacion_id == organizacion_id)
        .order_by(Notificacion.creado_en.desc(), Notificacion.id.desc())
    )
    if limite is not None:
        consulta = consulta.limit(limite)
    return list(db.session.execute(consulta).scalars())


def contar_no_leidas(usuario_id: int) -> int:
    return sum(not notificacion.leida for notificacion in listar_para_usuario(usuario_id))


def marcar_como_leida(notificacion_id: int, usuario_id: int) -> Notificacion:
    """Marca el aviso como leído verificando que pertenezca a la organización del usuario."""
    from app.modulos.usuarios_roles.modelos import Usuario

    notificacion = db.session.get(Notificacion, notificacion_id)
    usuario = db.session.get(Usuario, usuario_id)
    if not notificacion or not usuario or not usuario.organizacion_id:
        raise RecursoNoEncontrado("No encontramos la notificación solicitada.")
    if notificacion.organizacion_id != usuario.organizacion_id:
        raise RecursoNoEncontrado("No encontramos la notificación solicitada.")
    notificacion.leida = True
    db.session.commit()
    return notificacion


def registrar_contexto(app) -> None:
    """Expone el resumen usado por el navbar en todas las plantillas."""
    from flask_login import current_user

    @app.context_processor
    def _notificaciones_de_la_sesion():
        if not current_user.is_authenticated:
            return {"notificaciones_recientes": [], "notificaciones_no_leidas": 0}
        recientes = listar_para_usuario(current_user.id, limite=3)
        return {
            "notificaciones_recientes": recientes,
            "notificaciones_no_leidas": contar_no_leidas(current_user.id),
        }
