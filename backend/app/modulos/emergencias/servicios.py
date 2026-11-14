"""Servicios de negocio del módulo de emergencias.

Implementa el eslabón 1 del enunciado:
registro de emergencias por parte de un municipio afectado,
con nivel de gravedad, zona afectada y descripción.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, case, func, select

from app.core.errores import (
    RecursoNoEncontrado,
    ReglaDeNegocioIncumplida,
    SolicitudInvalida,
)
from app.core.integraciones.bonita.proceso import iniciar_gestion as _bonita_iniciar
from app.core.logging import registrar_evento
from app.extensiones import db
from app.modulos.emergencias.modelos import (
    Emergencia,
    EstadoEmergencia,
    EstadoLote,
    Item,
    LoteItem,
    LoteNecesidad,
    NivelGravedad,
    TipoEmergencia,
    TipoNecesidad,
)
from app.modulos.notificaciones import servicios as servicios_de_notificaciones
from app.modulos.organizaciones.modelos import Organizacion, TipoOrganizacion
from app.modulos.usuarios_roles.modelos import Usuario

# Estados terminales: una emergencia en cualquier otro estado sigue en curso.
ESTADOS_CERRADOS = (EstadoEmergencia.finalizada, EstadoEmergencia.cancelada)


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
            f"La organización '{org.nombre}' debe ser de tipo municipio para registrar emergencias",
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
        tipo_emergencia=tipo,
    )


def _notificar_instanciacion_bonita(case_id: str | None, emergencia_id):
    if not case_id:
        registrar_evento(
            logging.WARNING,
            "bonita_start_event_error",
            emergencia_id=emergencia_id,
            motivo="No se pudo comunicar con Bonita."
            "Revisar conexión."
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
    tipo_emergencia: str,
) -> Emergencia:
    """Registra una nueva emergencia."""

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

    # NUEVO: obtener el usuario que está registrando la emergencia.

    usuario = db.session.get(Usuario, usuario_id)

    if usuario is None:
        raise RecursoNoEncontrado(f"Usuario con id {usuario_id} no encontrado.")

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

    _registrar_alta_de_emergencia(
        emergencia.id,
        municipio_id,
        gravedad.value,
        tipo.value,
    )

    # Disparar creación de una instancia de proceso en Bonita BPM.
    # Envía emergencia_id, recibe identificador del caso.

    try:
        # NUEVO: el email del usuario web es también su username en Bonita.
        case_id = _bonita_iniciar(
            emergencia.id,
            usuario.email,
        )
        emergencia.bonita_case_id = case_id
        db.session.commit()
        _notificar_instanciacion_bonita(case_id, emergencia.id)
    except Exception:
        # No diferencia entre SistemaExternoRechazo,
        # ServicioExternoNoDisponible y RuntimeError.
        # Lo importante es que aunque falle Bonita,
        # la emergencia se registre.
        # Puede volver a intentar conectar a la hora
        # de abrir convocatoria.
        db.session.rollback()
        _notificar_instanciacion_bonita(None, emergencia.id)

    # Servicio de notificación al Centro Coordinador Regional.

    servicios_de_notificaciones.crear_para_tipo_organizacion(
        tipo=TipoOrganizacion.centro_coordinador_regional,
        titulo="Nueva emergencia registrada",
        mensaje=(f"Se registró la emergencia «{emergencia.titulo}» en {emergencia.zona_afectada}."),
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
        .where(Emergencia.estado.not_in(ESTADOS_CERRADOS))
        .order_by(expresion_gravedad.desc(), Emergencia.creado_en.desc())
    )

    if municipio_id is not None:
        consulta = consulta.where(Emergencia.municipio_id == municipio_id)

    return list(db.session.execute(consulta).scalars().all())


# --- Lectura agregada (panel de auditoria) ---------------------------------------


@dataclass(frozen=True, slots=True)
class ConteoDeEmergencias:
    """Cuantas emergencias se registraron en un rango, segun en que quedo cada una."""

    registradas: int
    en_curso: int
    finalizadas: int
    canceladas: int


def _registradas_entre(desde: datetime, hasta: datetime):
    """Rango semiabierto `[desde, hasta)` sobre la fecha de registro.

    Los limites llegan en UTC: es como se guardan las fechas, y asi la comparacion es la misma
    en PostgreSQL y en el SQLite de los tests.
    """
    return (Emergencia.creado_en >= desde) & (Emergencia.creado_en < hasta)


def contar_emergencias_registradas(*, desde: datetime, hasta: datetime) -> ConteoDeEmergencias:
    """Cuenta en una sola consulta las emergencias registradas en `[desde, hasta)`."""

    def contar_si(condicion):
        return func.count(case((condicion, 1)))

    fila = db.session.execute(
        select(
            func.count(Emergencia.id),
            contar_si(Emergencia.estado.not_in(ESTADOS_CERRADOS)),
            contar_si(Emergencia.estado == EstadoEmergencia.finalizada),
            contar_si(Emergencia.estado == EstadoEmergencia.cancelada),
        ).where(_registradas_entre(desde, hasta))
    ).one()

    registradas, en_curso, finalizadas, canceladas = fila
    return ConteoDeEmergencias(
        registradas=registradas,
        en_curso=en_curso,
        finalizadas=finalizadas,
        canceladas=canceladas,
    )


def _filtro_de_registradas(
    desde: datetime,
    hasta: datetime,
    gravedad: NivelGravedad | None = None,
    estado: EstadoEmergencia | None = None,
):
    """Las registradas en `[desde, hasta)`, acotadas a una gravedad y un estado si se indican."""
    condicion = _registradas_entre(desde, hasta)
    if gravedad is not None:
        condicion &= Emergencia.nivel_gravedad == gravedad
    if estado is not None:
        condicion &= Emergencia.estado == estado
    return condicion


def contar_emergencias_por_estado(
    *, desde: datetime, hasta: datetime, gravedad: NivelGravedad | None = None
) -> dict[EstadoEmergencia, int]:
    """Cuantas emergencias registradas en `[desde, hasta)` hay en cada estado.

    Trae todos los estados, en el orden del ciclo de vida (el del enum) y con 0 los que no tienen
    emergencias: un estado nuevo aparece solo, sin tocar a quien consume el conteo.
    """
    filas = db.session.execute(
        select(Emergencia.estado, func.count(Emergencia.id))
        .where(_filtro_de_registradas(desde, hasta, gravedad))
        .group_by(Emergencia.estado)
    ).all()
    cantidades = {estado: cantidad for estado, cantidad in filas}
    return {estado: cantidades.get(estado, 0) for estado in EstadoEmergencia}


def consultar_ids_de_emergencias_registradas(
    *,
    desde: datetime,
    hasta: datetime,
    gravedad: NivelGravedad | None = None,
    estado: EstadoEmergencia | None = None,
) -> Select[tuple[int]]:
    """Subconsulta con los ids de las emergencias registradas en `[desde, hasta)`.

    Es la forma en que los demas modulos filtran "las emergencias del periodo" sin conocer esta
    tabla: la usan como `emergencia_id.in_(...)` y todo se resuelve en una sola consulta.
    `gravedad` y `estado` acotan el conjunto cuando se indican.
    """
    return select(Emergencia.id).where(_filtro_de_registradas(desde, hasta, gravedad, estado))


def consultar_unidades_requeridas(
    *, emergencia_ids: Select[tuple[int]]
) -> Select[tuple[int, int, int, int, TipoNecesidad]]:
    """Subconsulta con las unidades que pide cada item de lote de esas emergencias.

    Columnas: `lote_item_id`, `emergencia_id`, `lote_id`, `cantidad_requerida` y `categoria` (el
    rubro del item del catalogo). Los lotes cancelados no cuentan: lo que se dejo de pedir ya no
    es una necesidad. Es un `Select` para que quien la use la combine con sus propios datos en
    una sola consulta, tomando solo las columnas que necesite.
    """
    return (
        select(
            LoteItem.id.label("lote_item_id"),
            LoteNecesidad.emergencia_id.label("emergencia_id"),
            LoteItem.lote_id.label("lote_id"),
            LoteItem.cantidad_solicitada.label("cantidad_requerida"),
            Item.categoria.label("categoria"),
        )
        .join(LoteNecesidad, LoteItem.lote_id == LoteNecesidad.id)
        .join(Item, LoteItem.item_id == Item.id)
        .where(
            LoteNecesidad.emergencia_id.in_(emergencia_ids),
            LoteNecesidad.estado != EstadoLote.cancelado,
        )
    )


@dataclass(frozen=True, slots=True)
class RegistroDeEmergencia:
    """Lo que necesitan los indicadores de tiempos de una emergencia, sin exponer el modelo.

    `creado_en` es la fecha de registro (el inicio de la respuesta) y `bonita_case_id` el caso del
    proceso en Bonita, o None si la emergencia nunca llego a instanciarlo.
    """

    id: int
    nivel_gravedad: NivelGravedad
    estado: EstadoEmergencia
    creado_en: datetime
    bonita_case_id: str | None


def listar_registros_de_emergencias(
    *, desde: datetime, hasta: datetime, gravedad: NivelGravedad | None = None
) -> list[RegistroDeEmergencia]:
    """Las emergencias registradas en `[desde, hasta)`, en una sola consulta y por fecha."""
    filas = db.session.execute(
        select(
            Emergencia.id,
            Emergencia.nivel_gravedad,
            Emergencia.estado,
            Emergencia.creado_en,
            Emergencia.bonita_case_id,
        )
        .where(_filtro_de_registradas(desde, hasta, gravedad))
        .order_by(Emergencia.creado_en, Emergencia.id)
    ).all()
    return [RegistroDeEmergencia(*fila) for fila in filas]


@dataclass(frozen=True, slots=True)
class DatosBasicosDeEmergencia:
    """Lo minimo para nombrar una emergencia en un reporte, sin exponer el modelo."""

    id: int
    titulo: str
    nivel_gravedad: NivelGravedad


def obtener_datos_basicos(ids: Iterable[int]) -> dict[int, DatosBasicosDeEmergencia]:
    """Titulo y gravedad de cada emergencia indicada, por id."""
    ids = list(ids)
    if not ids:
        return {}
    filas = db.session.execute(
        select(Emergencia.id, Emergencia.titulo, Emergencia.nivel_gravedad).where(
            Emergencia.id.in_(ids)
        )
    ).all()
    return {id_: DatosBasicosDeEmergencia(id_, titulo, gravedad) for id_, titulo, gravedad in filas}
