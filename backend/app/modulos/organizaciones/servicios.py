"""Logica de negocio de municipios, ONGs y centros coordinadores.

Es el **unico punto de entrada** al que pueden llamar los demas modulos para saber algo de una
organizacion: nadie importa `modelos.py` de aca (regla 4 de docs/arquitectura/componentes.md).
En particular `usuarios_roles` usa `obtener_tipo_de_organizacion()` para verificar que el rol
de una cuenta case con el tipo de la organizacion a la que se la asocia.

Por que este modulo va primero en la cadena de dependencias
-----------------------------------------------------------
Sin una organizacion cargada no se puede crear un operador municipal ni un representante de
ONG, asi que `usuarios_roles` depende de `organizaciones` y no al reves.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, select

from app.core.errores import ConflictoDeEstado, RecursoNoEncontrado, SolicitudInvalida
from app.core.paginacion import Pagina, paginar
from app.extensiones import db
from app.modulos.organizaciones.modelos import Organizacion, TipoOrganizacion

MENSAJE_NOMBRE_EN_USO = "Ya existe una organización registrada con ese nombre."
MENSAJE_IDENTIFICADOR_EN_USO = "Ya existe una organización con ese identificador nacional."
MENSAJE_NO_ENCONTRADA = "No encontramos la organización solicitada."


def _normalizar_texto(valor: str | None) -> str | None:
    """Recorta espacios y convierte la cadena vacia en ausencia de dato."""
    if valor is None:
        return None
    limpio = valor.strip()
    return limpio or None


def convertir_tipo(valor: str | TipoOrganizacion) -> TipoOrganizacion:
    """Traduce el nombre del tipo al enum, con un error de validacion claro si no existe."""
    if isinstance(valor, TipoOrganizacion):
        return valor
    try:
        return TipoOrganizacion(str(valor).strip())
    except ValueError:
        validos = ", ".join(tipo.value for tipo in TipoOrganizacion)
        raise SolicitudInvalida(
            detalle={"tipo": [f"Tipo de organización inválido. Valores admitidos: {validos}."]}
        ) from None


def obtener(organizacion_id: int) -> Organizacion:
    """Devuelve la organizacion o corta con 404."""
    organizacion = db.session.get(Organizacion, organizacion_id)
    if organizacion is None:
        raise RecursoNoEncontrado(MENSAJE_NO_ENCONTRADA)
    return organizacion


def obtener_tipo_de_organizacion(organizacion_id: int) -> str | None:
    """Tipo de la organizacion como string, o None si no existe.

    Devuelve el *valor* del enum y no el enum para que `usuarios_roles` pueda verificar la
    coherencia entre rol y organizacion sin importar los modelos de este modulo.
    """
    tipo = db.session.execute(
        select(Organizacion.tipo).where(Organizacion.id == organizacion_id)
    ).scalar_one_or_none()
    return None if tipo is None else tipo.value


def esta_activa(organizacion_id: int) -> bool:
    """Indica si la organizacion existe y esta habilitada para operar."""
    activo = db.session.execute(
        select(Organizacion.activo).where(Organizacion.id == organizacion_id)
    ).scalar_one_or_none()
    return bool(activo)


def listar(
    *,
    tipo: str | None = None,
    activo: bool | None = None,
    texto: str | None = None,
) -> list[Organizacion]:
    """Listado completo, sin paginar (por ejemplo, para un select). Filtros con AND."""
    consulta = _consulta(tipo=tipo, activo=activo, texto=texto)
    return list(db.session.execute(consulta).scalars())


def paginar_listado(
    *,
    pagina: int,
    por_pagina: int,
    tipo: str | None = None,
    activo: bool | None = None,
    texto: str | None = None,
) -> Pagina[Organizacion]:
    """Una pagina del listado de organizaciones, con los mismos filtros que `listar`."""
    return paginar(_consulta(tipo=tipo, activo=activo, texto=texto), pagina, por_pagina)


def _consulta(*, tipo: str | None, activo: bool | None, texto: str | None) -> Select:
    # El id desempata para que el orden sea total y la paginacion, estable.
    consulta = select(Organizacion).order_by(Organizacion.nombre, Organizacion.id)

    if tipo is not None:
        consulta = consulta.where(Organizacion.tipo == convertir_tipo(tipo))
    if activo is not None:
        consulta = consulta.where(Organizacion.activo.is_(activo))
    if texto:
        consulta = consulta.where(Organizacion.nombre.ilike(f"%{texto.strip()}%"))

    return consulta


def _verificar_nombre_disponible(nombre: str, excluir_id: int | None = None) -> None:
    consulta = select(Organizacion.id).where(Organizacion.nombre == nombre)
    if excluir_id is not None:
        consulta = consulta.where(Organizacion.id != excluir_id)
    if db.session.execute(consulta).scalar_one_or_none() is not None:
        raise ConflictoDeEstado(MENSAJE_NOMBRE_EN_USO)


def _verificar_identificador_disponible(
    identificador: str | None, excluir_id: int | None = None
) -> None:
    if identificador is None:
        return
    consulta = select(Organizacion.id).where(Organizacion.identificador_nacional == identificador)
    if excluir_id is not None:
        consulta = consulta.where(Organizacion.id != excluir_id)
    if db.session.execute(consulta).scalar_one_or_none() is not None:
        raise ConflictoDeEstado(MENSAJE_IDENTIFICADOR_EN_USO)


def crear(
    *,
    nombre: str,
    tipo: str | TipoOrganizacion,
    identificador_nacional: str | None = None,
    contacto_email: str | None = None,
    contacto_telefono: str | None = None,
    direccion: str | None = None,
) -> Organizacion:
    """Da de alta una organizacion. La deja activa."""
    nombre_limpio = nombre.strip()
    identificador = _normalizar_texto(identificador_nacional)

    _verificar_nombre_disponible(nombre_limpio)
    _verificar_identificador_disponible(identificador)

    organizacion = Organizacion(
        nombre=nombre_limpio,
        tipo=convertir_tipo(tipo),
        identificador_nacional=identificador,
        contacto_email=_normalizar_texto(contacto_email),
        contacto_telefono=_normalizar_texto(contacto_telefono),
        direccion=_normalizar_texto(direccion),
        activo=True,
    )
    db.session.add(organizacion)
    db.session.commit()
    return organizacion


def editar(
    organizacion_id: int,
    *,
    nombre: str,
    tipo: str | TipoOrganizacion,
    identificador_nacional: str | None = None,
    contacto_email: str | None = None,
    contacto_telefono: str | None = None,
    direccion: str | None = None,
) -> Organizacion:
    """Actualiza los datos de una organizacion existente."""
    organizacion = obtener(organizacion_id)

    nombre_limpio = nombre.strip()
    identificador = _normalizar_texto(identificador_nacional)

    _verificar_nombre_disponible(nombre_limpio, excluir_id=organizacion.id)
    _verificar_identificador_disponible(identificador, excluir_id=organizacion.id)

    organizacion.nombre = nombre_limpio
    organizacion.tipo = convertir_tipo(tipo)
    organizacion.identificador_nacional = identificador
    organizacion.contacto_email = _normalizar_texto(contacto_email)
    organizacion.contacto_telefono = _normalizar_texto(contacto_telefono)
    organizacion.direccion = _normalizar_texto(direccion)

    db.session.commit()
    return organizacion


def cambiar_estado(organizacion_id: int, *, activo: bool) -> Organizacion:
    """Alta o baja logica.

    No se borra nunca: las emergencias, ofertas y adjudicaciones ya registradas apuntan a la
    organizacion, y perderlas dejaria el historial del proceso incompleto.
    """
    organizacion = obtener(organizacion_id)
    organizacion.activo = activo
    db.session.commit()
    return organizacion


def a_diccionario(organizacion: Organizacion) -> dict[str, Any]:
    """Representacion de la organizacion para la respuesta HTTP.

    Es tambien lo que la plantilla va a recibir como contexto cuando exista la interfaz: la
    vista no cambia segun el formato de salida.
    """
    return {
        "id": organizacion.id,
        "nombre": organizacion.nombre,
        "tipo": organizacion.tipo.value,
        "identificador_nacional": organizacion.identificador_nacional,
        "contacto_email": organizacion.contacto_email,
        "contacto_telefono": organizacion.contacto_telefono,
        "direccion": organizacion.direccion,
        "activo": organizacion.activo,
        "creado_en": organizacion.creado_en.isoformat() if organizacion.creado_en else None,
    }
