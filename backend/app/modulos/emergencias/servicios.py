"""Servicios de negocio del módulo de emergencias.

Implementa el eslabón 1 del enunciado:
registro de emergencias por parte de un municipio afectado,
con nivel de gravedad, zona afectada y descripción.
"""

from __future__ import annotations

import logging

from sqlalchemy import case, select

from app.core.errores import (
    RecursoNoEncontrado,
    ReglaDeNegocioIncumplida,
    SolicitudInvalida,
)
from app.core.logging import registrar_evento
from app.extensiones import db
from app.modulos.emergencias.modelos import (
    Emergencia,
    EstadoEmergencia,
    NivelGravedad,
    TipoEmergencia
)
from app.modulos.notificaciones import servicios as servicios_de_notificaciones
from app.modulos.organizaciones.modelos import Organizacion, TipoOrganizacion

from app.core.integraciones.bonita.proceso import iniciar_gestion as _bonita_iniciar

def _validar_municipio(municipio_id: int) -> Organizacion:
    """Valida que la organización exista, esté activa y sea de tipo municipio."""
    if not municipio_id:
        raise SolicitudInvalida(
            "Debe especificarse el municipio que registra la emergencia.",
            detalle={"campo": "municipio_id"},
        )

    org = db.session.get(Organizacion, municipio_id)
    if not org:
        raise RecursoNoEncontrado(f"No se encuentró ninguna organización con id {municipio_id}.")

    if not org.activo:
        raise ReglaDeNegocioIncumplida(
            f"La organización '{org.nombre}' no se encuentra activa.",
            detalle={"municipio_id": org.id},
        )

    if org.tipo != TipoOrganizacion.municipio:
        raise ReglaDeNegocioIncumplida(
            f"La organización '{org.nombre}' debe ser de tipo municipio para registrar emergencias.",
            detalle={"municipio_id": org.id, "tipo": org.tipo.value},
        )

    return org


def _normalizar_nivel_gravedad(valor: str) -> NivelGravedad:
    """Convierte el valor del formulario al enum correspondiente."""
    try:
        return NivelGravedad(valor)
    except ValueError as error:
        opciones = ", ".join(n.value for n in NivelGravedad)
        raise SolicitudInvalida(
            f"Nivel de gravedad inválido. Opciones: {opciones}.",
            detalle={"campo": "nivel_gravedad"},
        ) from error


def _normalizar_tipo_emergencia(valor: str) -> TipoEmergencia:
    """Convierte el valor del formulario al enum correspondiente."""
    try:
        return TipoEmergencia(valor)
    except ValueError as error:
        opciones = ", ".join(n.value for n in TipoEmergencia)
        raise SolicitudInvalida(
            f"Tipo de emergencia inválido. Opciones: {opciones}.",
            detalle={"campo": "tipo_emergencia"},
        ) from error


def _registrar_alta_de_emergencia(emergencia, municipio, gravedad, tipo):
        registrar_evento(
        logging.INFO,
        "emergencia_creada",
        emergencia_id=emergencia,
        municipio_id=municipio,
        nivel_gravedad=gravedad,
        tipo_emergencia=tipo
    )

        
def _notificar_instanciacion_bonita(case_id: str | None, emergencia_id):
    if not case_id:
        registrar_evento(
            logging.WARNING,
            "bonita_start_event_error",
            emergencia_id=emergencia_id,
            motivo=f"No se pudo comunicar con Bonita." \
            "Revisar conexión." \
            "La emergencia se dio de alta localmente, aunque sin instancia de proceso.",
        )
    else:
        registrar_evento(
            logging.INFO,
            "bonita_start_event",
            emergencia_id=emergencia_id,
            bonita_case_id=case_id,
        )


def crear_emergencia(
    *,
    titulo: str,
    descripcion: str,
    nivel_gravedad: str,
    zona_afectada: str,
    municipio_id: int,
    usuario_id: int,
    tipo_emergencia: str
) -> Emergencia:
    """Registra una nueva emergencia.
    """

    # Validación de campos

    titulo = (titulo or "").strip()
    descripcion = (descripcion or "").strip()
    zona_afectada = (zona_afectada or "").strip()

    errores: dict[str, str] = {}
    if not titulo:
        errores["titulo"] = "El título es obligatorio."
    elif len(titulo) > 200:
        errores["titulo"] = "El título no puede superar los 200 caracteres."

    if not descripcion:
        errores["descripcion"] = "La descripción es obligatoria."

    if not zona_afectada:
        errores["zona_afectada"] = "La zona afectada es obligatoria."
    elif len(zona_afectada) > 255:
        errores["zona_afectada"] = "La zona afectada no puede superar los 255 caracteres."

    if errores:
        raise SolicitudInvalida(
            "Revisá los campos del formulario.",
            detalle=errores,
        )

    _validar_municipio(municipio_id)
    gravedad = _normalizar_nivel_gravedad(nivel_gravedad)
    tipo = _normalizar_tipo_emergencia(tipo_emergencia)
    
    # Alta de emergencia

    emergencia = Emergencia(
        titulo=titulo,
        descripcion=descripcion,
        nivel_gravedad=gravedad,
        zona_afectada=zona_afectada,
        estado=EstadoEmergencia.registrada,
        municipio_id=municipio_id,
        usuario_id=usuario_id,
        tipo_emergencia=tipo,
    )
    db.session.add(emergencia)
    db.session.commit()

    # Registrar evento de alta de emergencia

    _registrar_alta_de_emergencia(emergencia.id, municipio_id, gravedad.value, tipo.value)
        
    # Disparar creación de una instancia de proceso en Bonita BPM.
    # Envía emergencia_id, recibe identificador del caso. 

    try:
        case_id = _bonita_iniciar(emergencia.id)
        emergencia.bonita_case_id = case_id
        db.session.commit()
        _notificar_instanciacion_bonita(case_id, emergencia.id) 
    except Exception:
        # No diferencia entre SistemaExternoRechazo, ServicioExternoNoDisponible y RuntimeError.
        # Lo importante es que aunque falle Bonita, la emergencia se registre.
        # Puede volver a intentar conectar a la hora de abrir convocatoria.
        db.session.rollback()
        _notificar_instanciacion_bonita(None, emergencia.id)
    

    # Servicio de notificación al Centro Coordinador Regional.

    servicios_de_notificaciones.crear_para_tipo_organizacion(
        tipo=TipoOrganizacion.centro_coordinador_regional,
        titulo="Nueva emergencia registrada",
        mensaje=f"Se registró la emergencia «{emergencia.titulo}» en {emergencia.zona_afectada}.",
        enlace=f"/emergencias/{emergencia.id}",
    )
    db.session.commit()

    return emergencia


def obtener_emergencia_por_id(emergencia_id: int) -> Emergencia:
    emergencia = db.session.get(Emergencia, emergencia_id)
    if not emergencia:
        raise RecursoNoEncontrado(f"Emergencia con id {emergencia_id} no encontrada.")
    return emergencia

# Nivel de gravedad vuelto número para poder usar order_by().
# A más alto el número, más urgente.
_NIVEL_GRAVEDAD = {
    NivelGravedad.baja: 1,
    NivelGravedad.media: 2,
    NivelGravedad.alta: 3,
    NivelGravedad.critica: 4,
}

def listar_emergencias(
    *,
    municipio_id: int | None = None,
) -> list[Emergencia]:
    """Lista emergencias ordenadas por gravedad, desempata por fecha."""
    expresion_gravedad = case(
        _NIVEL_GRAVEDAD,
        value=Emergencia.nivel_gravedad,
        else_=0,
    )

    consulta = (
        select(Emergencia)
        .where(Emergencia.estado != EstadoEmergencia.finalizada, Emergencia.estado != EstadoEmergencia.cancelada )
        .order_by(expresion_gravedad.desc(), Emergencia.creado_en.desc())
    )

    if municipio_id is not None:
        consulta = consulta.where(Emergencia.municipio_id == municipio_id)

    return list(db.session.execute(consulta).scalars().all())