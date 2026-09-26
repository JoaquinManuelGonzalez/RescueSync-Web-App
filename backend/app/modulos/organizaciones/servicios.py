"""Logica de negocio de municipios, ONGs y centros coordinadores.

Es el **unico punto de entrada** al que pueden llamar los demas modulos para saber algo de una
organizacion: nadie importa `modelos.py` de aca (regla 4 de docs/arquitectura/componentes.md).
En particular `usuarios_roles` usa `obtener_tipo_de_organizacion()` para verificar que el rol
de una cuenta case con el tipo de la organizacion a la que se la asocia, y `esta_activa()` para
cortar el acceso de las cuentas de una organizacion dada de baja.

Por que este modulo va primero en la cadena de dependencias
-----------------------------------------------------------
Sin una organizacion cargada no se puede crear un operador municipal ni un representante de
ONG, asi que `usuarios_roles` depende de `organizaciones` y no al reves. Por eso `miembros()`
lee las cuentas a traves de la relacion `Organizacion.usuarios` y no importando nada de
`usuarios_roles`.

Zona de cobertura
-----------------
Se recibe como una lista de `{"provincia": ..., "localidad": ...}`. `normalizar_zonas()` valida
la provincia contra la lista cerrada de `geografia.PROVINCIAS`, separa las localidades escritas
con comas en una zona cada una, descarta filas vacias y repetidas, y absorbe las localidades de
una provincia que ya figura completa. Una ONG tiene que
declarar al menos una zona o marcar `cobertura_nacional` (opera en todo el pais, sin cargar las 24
jurisdicciones); para municipios y centros coordinadores es opcional.

Verificacion contra el Sistema Nacional
---------------------------------------
Las organizaciones se cargan en RescueSync despues de que el Sistema Nacional las verifico, asi
que toda alta nace `verificada` y editarla no cambia ese estado. Si la integracion con la API
Nacional llegara a informar otro resultado, lo guarda con `registrar_resultado_de_verificacion()`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import Select, func, or_, select

from app.core.errores import ConflictoDeEstado, RecursoNoEncontrado, SolicitudInvalida
from app.core.interfaz.paginacion import Pagina, paginar
from app.core.logging import id_correlacion_actual, registrar_evento
from app.extensiones import db
from app.modulos.emergencias.modelos import Item
from app.modulos.organizaciones.geografia import PROVINCIAS
from app.modulos.organizaciones.modelos import (
    EstadoVerificacion,
    Inventario,
    InventarioItem,
    Organizacion,
    TipoOrganizacion,
    ZonaDeCobertura,
)

MENSAJE_NOMBRE_EN_USO = "Ya existe una organización registrada con ese nombre."
MENSAJE_IDENTIFICADOR_EN_USO = "Ya existe una organización con ese identificador nacional."
MENSAJE_NO_ENCONTRADA = "No encontramos la organización solicitada."
MENSAJE_INVENTARIO_NO_ENCONTRADO = "No encontramos el inventario de la organización."
MENSAJE_ITEM_NO_ENCONTRADO = "No encontramos el item solicitado."
MENSAJE_ITEM_YA_CARGADO = "El item ya está cargado en el inventario."
MENSAJE_SIN_ORGANIZACION = "Tu cuenta no pertenece a ninguna organización."
MENSAJE_ONG_SIN_ZONAS = (
    "Una ONG tiene que declarar al menos una zona de cobertura o marcar que opera en todo el país."
)
# Limites de la cobertura. Una localidad cabe en la columna `localidad` (String(150)); el campo
# del formulario puede traer varias separadas por comas, hasta un largo razonable; y el total por
# organizacion tiene un techo para que un campo con cientos de comas no genere cientos de filas.
MAXIMO_DE_LOCALIDAD = 150
MAXIMO_DE_CARACTERES_DE_LOCALIDADES = 1000
MAXIMO_DE_ZONAS_POR_ORGANIZACION = 200

MENSAJE_TIPO_CON_MIEMBROS = (
    "No se puede cambiar el tipo: la organización tiene {cantidad} cuenta(s) vinculada(s). "
    "Reasignalas a otra organización antes de cambiarlo."
)


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


def convertir_estado_verificacion(valor: str | EstadoVerificacion) -> EstadoVerificacion:
    """Traduce el nombre del estado de verificacion al enum, con un error claro si no existe."""
    if isinstance(valor, EstadoVerificacion):
        return valor
    try:
        return EstadoVerificacion(str(valor).strip())
    except ValueError:
        validos = ", ".join(estado.value for estado in EstadoVerificacion)
        raise SolicitudInvalida(
            detalle={
                "estado_verificacion": [
                    f"Estado de verificación inválido. Valores admitidos: {validos}."
                ]
            }
        ) from None


def _separar_localidades(texto: str) -> list[str]:
    """Parte "La Plata, Berisso,  Los Hornos" en ["La Plata", "Berisso", "Los Hornos"].

    La coma siempre separa: no hay localidades argentinas cuyo nombre la lleve. Cada nombre se
    recorta y se le colapsan los espacios internos; los tramos vacios (",," o una coma al final)
    se descartan.
    """
    return [nombre for tramo in texto.split(",") if (nombre := " ".join(tramo.split()))]


def normalizar_zonas(
    zonas: Iterable[Mapping[str, Any]] | None,
) -> list[tuple[str, str | None]]:
    """Valida y deja en forma canonica las zonas de cobertura.

    - Las filas sin provincia ni localidad se ignoran: son las filas vacias del formulario.
    - La provincia tiene que ser una de `geografia.PROVINCIAS`.
    - La localidad admite varias separadas por comas ("La Plata, Berisso"): cada una se guarda
      como una zona propia. Un campo con solo comas es un error, no "toda la provincia".
    - Cada localidad se recorta y se le colapsan los espacios; dos que solo difieren en
      mayusculas son la misma, en la misma fila o en filas distintas.
    - Si una provincia figura completa (sin localidad), sus localidades sueltas sobran.
    - Una organizacion admite hasta `MAXIMO_DE_ZONAS_POR_ORGANIZACION` zonas.

    Devuelve pares (provincia, localidad) ordenados, listos para persistir.
    """
    errores: list[str] = []
    provincias_completas: set[str] = set()
    localidades: dict[tuple[str, str], str] = {}

    for numero, zona in enumerate(zonas or [], start=1):
        provincia_cruda, localidad_cruda = zona.get("provincia"), zona.get("localidad")
        if not all(
            valor is None or isinstance(valor, str) for valor in (provincia_cruda, localidad_cruda)
        ):
            errores.append(f"Zona {numero}: provincia y localidad tienen que ser texto.")
            continue
        provincia = _normalizar_texto(provincia_cruda)
        texto_de_localidad = _normalizar_texto(localidad_cruda)

        if provincia is None and texto_de_localidad is None:
            continue
        if provincia is None:
            errores.append(f"Zona {numero}: indicá la provincia de «{texto_de_localidad}».")
            continue
        if provincia not in PROVINCIAS:
            errores.append(f"Zona {numero}: «{provincia}» no es una provincia válida.")
            continue
        if texto_de_localidad is None:
            provincias_completas.add(provincia)
            continue
        if len(texto_de_localidad) > MAXIMO_DE_CARACTERES_DE_LOCALIDADES:
            errores.append(
                f"Zona {numero}: el campo de localidades admite hasta "
                f"{MAXIMO_DE_CARACTERES_DE_LOCALIDADES} caracteres. Repartilas en más filas."
            )
            continue

        nombres = _separar_localidades(texto_de_localidad)
        if not nombres:
            errores.append(
                f"Zona {numero}: «{texto_de_localidad}» no tiene ninguna localidad. Escribí los "
                "nombres separados por comas, o dejá el campo vacío para toda la provincia."
            )
            continue
        demasiado_largos = [nombre for nombre in nombres if len(nombre) > MAXIMO_DE_LOCALIDAD]
        if demasiado_largos:
            errores.extend(
                f"Zona {numero}: «{nombre[:40]}…» supera los {MAXIMO_DE_LOCALIDAD} caracteres "
                "de una localidad."
                for nombre in demasiado_largos
            )
            continue
        for nombre in nombres:
            localidades.setdefault((provincia, nombre.casefold()), nombre)

    if errores:
        raise SolicitudInvalida(detalle={"zonas": errores})

    resultado: list[tuple[str, str | None]] = [(p, None) for p in provincias_completas]
    resultado.extend(
        (provincia, localidad)
        for (provincia, _), localidad in localidades.items()
        if provincia not in provincias_completas
    )
    if len(resultado) > MAXIMO_DE_ZONAS_POR_ORGANIZACION:
        raise SolicitudInvalida(
            detalle={
                "zonas": [
                    f"Se declararon {len(resultado)} zonas y el máximo es "
                    f"{MAXIMO_DE_ZONAS_POR_ORGANIZACION}. Si la organización cubre provincias "
                    "enteras, dejá la localidad vacía; si opera en todo el país, marcalo."
                ]
            }
        )
    return sorted(resultado, key=lambda zona: (zona[0], zona[1] or ""))


def zonas_agrupadas_por_provincia(
    zonas: Iterable[tuple[str, str | None]],
) -> list[dict[str, str | None]]:
    """La inversa de `normalizar_zonas()` para el formulario: una fila por provincia.

    Las localidades de una misma provincia vuelven a juntarse separadas por comas, que es como
    se cargaron; la provincia completa queda con la localidad vacia.
    """
    por_provincia: dict[str, list[str]] = {}
    for provincia, localidad in zonas:
        lista = por_provincia.setdefault(provincia, [])
        if localidad is not None:
            lista.append(localidad)
    return [
        {"provincia": provincia, "localidad": ", ".join(nombres) or None}
        for provincia, nombres in sorted(por_provincia.items())
    ]


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

def obtener_inventario(organizacion_id: int) -> Inventario | None:
    """Devuelve el inventario de la organizacion."""
    return db.session.execute(
        select(Inventario).where(Inventario.organizacion_id == organizacion_id)
    ).scalar_one_or_none()


def paginar_items_de_inventario(
    organizacion_id: int,
    categoria: str | None = None,
    texto: str | None = None,
    *,
    pagina: int,
    por_pagina: int,
):
    """Devuelve una pagina de items, filtrada opcionalmente por categoria y nombre."""
    consulta = (
        select(InventarioItem)
        .join(Inventario)
        .join(Item)
        .where(Inventario.organizacion_id == organizacion_id)
        .order_by(Item.nombre)
    )
    if categoria:
        consulta = consulta.where(Item.categoria == categoria)
    if texto:
        consulta = consulta.where(Item.nombre.ilike(f"%{texto.strip()}%"))
    return paginar(consulta, pagina, por_pagina)


def categorias_de_inventario(organizacion_id: int) -> list[tuple[str, str]]:
    """Devuelve las categorias presentes en el inventario, con valor y etiqueta."""
    consulta = (
        select(Item.categoria)
        .join(InventarioItem, InventarioItem.item_id == Item.id)
        .join(Inventario, Inventario.id == InventarioItem.inventario_id)
        .where(Inventario.organizacion_id == organizacion_id)
        .distinct()
        .order_by(Item.categoria)
    )
    return [
        (categoria.value, categoria.value.replace("_", " ").title())
        for categoria in db.session.scalars(consulta)
    ]


def listar_items() -> list[Item]:
    """Devuelve el catalogo de items ordenado para los formularios."""
    return list(db.session.scalars(select(Item).order_by(Item.nombre)))


def listar_items_disponibles(organizacion_id: int) -> list[Item]:
    """Devuelve los items que aun no fueron cargados en el inventario indicado."""
    items_cargados = select(InventarioItem.item_id).join(Inventario).where(
        Inventario.organizacion_id == organizacion_id
    )
    consulta = select(Item).where(~Item.id.in_(items_cargados)).order_by(Item.nombre)
    return list(db.session.scalars(consulta))


def crear_item_inventario(
    organizacion_id: int,
    *,
    item_id: int,
    cantidad_disponible,
) -> InventarioItem:
    """Agrega un item al inventario de la organizacion."""
    inventario = obtener_inventario(organizacion_id)
    if inventario is None:
        raise RecursoNoEncontrado(MENSAJE_INVENTARIO_NO_ENCONTRADO)

    if db.session.get(Item, item_id) is None:
        raise RecursoNoEncontrado(MENSAJE_ITEM_NO_ENCONTRADO)

    existente = db.session.execute(
        select(InventarioItem).where(
            InventarioItem.inventario_id == inventario.id,
            InventarioItem.item_id == item_id,
        )
    ).scalar_one_or_none()
    if existente is not None:
        raise ConflictoDeEstado(MENSAJE_ITEM_YA_CARGADO)

    inventario_item = InventarioItem(
        inventario_id=inventario.id,
        item_id=item_id,
        cantidad_disponible=cantidad_disponible,
    )
    db.session.add(inventario_item)
    db.session.commit()
    return inventario_item


def obtener_item_inventario(
    organizacion_id: int,
    inventario_item_id: int,
) -> InventarioItem:
    """Devuelve un item del inventario de la organizacion o corta con 404."""
    inventario_item = db.session.execute(
        select(InventarioItem)
        .join(Inventario)
        .where(
            InventarioItem.id == inventario_item_id,
            Inventario.organizacion_id == organizacion_id,
        )
    ).scalar_one_or_none()
    if inventario_item is None:
        raise RecursoNoEncontrado(MENSAJE_ITEM_NO_ENCONTRADO)
    return inventario_item


def editar_item_inventario(
    organizacion_id: int,
    inventario_item_id: int,
    *,
    item_id: int,
    cantidad_disponible,
) -> InventarioItem:
    """Actualiza la cantidad de un item del inventario de la organizacion."""
    inventario_item = obtener_item_inventario(organizacion_id, inventario_item_id)
    if inventario_item.item_id != item_id:
        raise SolicitudInvalida(detalle={"item_id": ["El item no coincide con el inventario."]})

    inventario_item.cantidad_disponible = cantidad_disponible
    db.session.commit()
    return inventario_item


def eliminar_item_inventario(
    organizacion_id: int,
    inventario_item_id: int,
) -> None:
    """Quita un item del inventario de la organizacion, sin borrar el item del catalogo."""
    inventario_item = obtener_item_inventario(organizacion_id, inventario_item_id)
    db.session.delete(inventario_item)
    db.session.commit()


def item_inventario_a_diccionario(inventario_item: InventarioItem) -> dict[str, Any]:
    """Representacion de un item de inventario para la respuesta HTTP."""
    return {
        "id": inventario_item.id,
        "inventario_id": inventario_item.inventario_id,
        "item_id": inventario_item.item_id,
        "cantidad_disponible": int(inventario_item.cantidad_disponible),
    }


def esta_activa(organizacion_id: int) -> bool:
    """Indica si la organizacion existe y esta habilitada para operar."""
    activo = db.session.execute(
        select(Organizacion.activo).where(Organizacion.id == organizacion_id)
    ).scalar_one_or_none()
    return bool(activo)


def obtener_propia(organizacion_id: int | None) -> Organizacion:
    """La organizacion de la cuenta en sesion, o 404 si la cuenta no pertenece a ninguna."""
    if organizacion_id is None:
        raise RecursoNoEncontrado(MENSAJE_SIN_ORGANIZACION)
    return obtener(organizacion_id)


def listar(
    *,
    tipo: str | None = None,
    activo: bool | None = None,
    texto: str | None = None,
    provincia: str | None = None,
) -> list[Organizacion]:
    """Listado completo, sin paginar (por ejemplo, para un select). Filtros con AND."""
    consulta = _consulta(
        tipo=tipo,
        activo=activo,
        texto=texto,
        provincia=provincia,
    )
    return list(db.session.execute(consulta).scalars())


def paginar_listado(
    *,
    pagina: int,
    por_pagina: int,
    tipo: str | None = None,
    activo: bool | None = None,
    texto: str | None = None,
    provincia: str | None = None,
) -> Pagina[Organizacion]:
    """Una pagina del listado de organizaciones, con los mismos filtros que `listar`."""
    consulta = _consulta(
        tipo=tipo,
        activo=activo,
        texto=texto,
        provincia=provincia,
    )
    return paginar(consulta, pagina, por_pagina)


def _consulta(
    *,
    tipo: str | None,
    activo: bool | None,
    texto: str | None,
    provincia: str | None = None,
) -> Select:
    # El id desempata para que el orden sea total y la paginacion, estable.
    consulta = select(Organizacion).order_by(Organizacion.nombre, Organizacion.id)

    if tipo is not None:
        consulta = consulta.where(Organizacion.tipo == convertir_tipo(tipo))
    if activo is not None:
        consulta = consulta.where(Organizacion.activo.is_(activo))
    if provincia:
        # Quien opera en todo el pais cubre cualquier provincia.
        consulta = consulta.where(
            or_(
                Organizacion.cobertura_nacional.is_(True),
                Organizacion.zonas_de_cobertura.any(ZonaDeCobertura.provincia == provincia.strip()),
            )
        )
    if texto:
        patron = f"%{texto.strip()}%"
        consulta = consulta.where(
            or_(
                Organizacion.nombre.ilike(patron),
                Organizacion.identificador_nacional.ilike(patron),
                Organizacion.contacto_email.ilike(patron),
                Organizacion.zonas_de_cobertura.any(ZonaDeCobertura.localidad.ilike(patron)),
            )
        )

    return consulta


def _verificar_nombre_disponible(nombre: str, excluir_id: int | None = None) -> None:
    # Sin distinguir mayusculas, igual que el indice `uq_organizacion_nombre_normalizado`.
    consulta = select(Organizacion.id).where(func.lower(Organizacion.nombre) == nombre.lower())
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


def _resolver_cobertura(
    tipo: TipoOrganizacion,
    zonas: list[tuple[str, str | None]],
    cobertura_nacional: bool,
) -> list[tuple[str, str | None]]:
    """Las zonas que corresponde guardar.

    La cobertura nacional reemplaza a las zonas: guardar ademas provincias sueltas seria
    redundante y haria que dejaran de coincidir si despues se desmarca. Sin cobertura nacional,
    una ONG tiene que declarar al menos una zona.
    """
    if cobertura_nacional:
        return []
    if tipo is TipoOrganizacion.ong and not zonas:
        raise SolicitudInvalida(detalle={"zonas": [MENSAJE_ONG_SIN_ZONAS]})
    return zonas


def _reemplazar_zonas(organizacion: Organizacion, zonas: list[tuple[str, str | None]]) -> None:
    """Deja en la organizacion exactamente estas zonas.

    Conserva las filas que ya existian y solo agrega o quita las que cambian: borrar todo y
    volver a insertar chocaria con la restriccion unica dentro del mismo flush.
    """
    deseadas = set(zonas)
    for zona in list(organizacion.zonas_de_cobertura):
        if (zona.provincia, zona.localidad) not in deseadas:
            organizacion.zonas_de_cobertura.remove(zona)
    actuales = {(zona.provincia, zona.localidad) for zona in organizacion.zonas_de_cobertura}
    for provincia, localidad in zonas:
        if (provincia, localidad) not in actuales:
            organizacion.zonas_de_cobertura.append(
                ZonaDeCobertura(provincia=provincia, localidad=localidad)
            )


def _asegurar_inventario(organizacion: Organizacion) -> None:
    """Toda ONG tiene inventario: sin el, su representante no podria cargar existencias.

    Solo crea la fila vacia; las existencias las gestiona la pantalla de inventario.
    """
    if organizacion.tipo is not TipoOrganizacion.ong:
        return
    if obtener_inventario(organizacion.id) is not None:
        return
    db.session.add(
        Inventario(
            organizacion_id=organizacion.id,
            nombre=f"Inventario de {organizacion.nombre}"[:150],
        )
    )


def crear(
    *,
    nombre: str,
    tipo: str | TipoOrganizacion,
    identificador_nacional: str | None = None,
    contacto_email: str | None = None,
    contacto_telefono: str | None = None,
    direccion: str | None = None,
    zonas: Iterable[Mapping[str, Any]] | None = None,
    cobertura_nacional: bool = False,
) -> Organizacion:
    """Da de alta una organizacion. La deja activa y verificada.

    La verificacion ya la hizo el Sistema Nacional antes de la carga. Si es una ONG, ademas le
    crea su inventario vacio.
    Con `cobertura_nacional=True` las zonas se ignoran: opera en todo el pais.
    """
    nombre_limpio = nombre.strip()
    identificador = _normalizar_texto(identificador_nacional)
    tipo_convertido = convertir_tipo(tipo)

    _verificar_nombre_disponible(nombre_limpio)
    _verificar_identificador_disponible(identificador)
    zonas_normalizadas = _resolver_cobertura(
        tipo_convertido, normalizar_zonas(zonas), cobertura_nacional
    )

    organizacion = Organizacion(
        nombre=nombre_limpio,
        tipo=tipo_convertido,
        identificador_nacional=identificador,
        contacto_email=_normalizar_texto(contacto_email),
        contacto_telefono=_normalizar_texto(contacto_telefono),
        direccion=_normalizar_texto(direccion),
        activo=True,
        cobertura_nacional=cobertura_nacional,
        estado_verificacion=EstadoVerificacion.verificada,
    )
    _reemplazar_zonas(organizacion, zonas_normalizadas)
    db.session.add(organizacion)
    db.session.flush()
    _asegurar_inventario(organizacion)
    db.session.commit()

    registrar_evento(
        logging.INFO,
        "organizacion_creada",
        id_organizacion=str(organizacion.id),
        tipo=organizacion.tipo.value,
        id_correlacion=id_correlacion_actual(),
    )
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
    zonas: Iterable[Mapping[str, Any]] | None = None,
    cobertura_nacional: bool | None = None,
) -> Organizacion:
    """Actualiza los datos de una organizacion existente.

    `zonas=None` y `cobertura_nacional=None` dejan la cobertura como esta (para llamadas desde la
    consola o el seeder); una lista, aunque este vacia, la reemplaza completa, que es lo que
    manda el formulario.

    El tipo no se puede cambiar mientras haya cuentas vinculadas: sus roles exigen el tipo actual
    (ver `permisos.TIPO_DE_ORGANIZACION_POR_ROL`). El estado de verificacion no se toca.
    """
    organizacion = obtener(organizacion_id)

    nombre_limpio = nombre.strip()
    identificador = _normalizar_texto(identificador_nacional)
    tipo_nuevo = convertir_tipo(tipo)
    nacional = organizacion.cobertura_nacional if cobertura_nacional is None else cobertura_nacional

    _verificar_nombre_disponible(nombre_limpio, excluir_id=organizacion.id)
    _verificar_identificador_disponible(identificador, excluir_id=organizacion.id)
    zonas_normalizadas = _resolver_cobertura(
        tipo_nuevo,
        (
            normalizar_zonas(zonas)
            if zonas is not None
            else [(zona.provincia, zona.localidad) for zona in organizacion.zonas_de_cobertura]
        ),
        nacional,
    )

    cambia_tipo = tipo_nuevo is not organizacion.tipo
    if cambia_tipo and organizacion.usuarios:
        mensaje = MENSAJE_TIPO_CON_MIEMBROS.format(cantidad=len(organizacion.usuarios))
        raise ConflictoDeEstado(mensaje, detalle={"tipo": [mensaje]})

    organizacion.nombre = nombre_limpio
    organizacion.tipo = tipo_nuevo
    organizacion.identificador_nacional = identificador
    organizacion.contacto_email = _normalizar_texto(contacto_email)
    organizacion.contacto_telefono = _normalizar_texto(contacto_telefono)
    organizacion.direccion = _normalizar_texto(direccion)
    organizacion.cobertura_nacional = nacional
    _reemplazar_zonas(organizacion, zonas_normalizadas)
    _asegurar_inventario(organizacion)

    db.session.commit()

    registrar_evento(
        logging.INFO,
        "organizacion_editada",
        id_organizacion=str(organizacion.id),
        id_correlacion=id_correlacion_actual(),
    )
    return organizacion


def editar_datos_propios(
    organizacion_id: int,
    *,
    contacto_email: str | None = None,
    contacto_telefono: str | None = None,
    direccion: str | None = None,
    zonas: Iterable[Mapping[str, Any]] | None = None,
    cobertura_nacional: bool | None = None,
) -> Organizacion:
    """Lo que un miembro puede actualizar de su propia organizacion: contacto y cobertura.

    Nombre, tipo, identificador, estado y verificacion quedan fuera a proposito: son los datos
    que hacen verificable al titular y solo los cambia el administrador (o la integracion).
    `cobertura_nacional=None` la deja como esta.
    """
    organizacion = obtener(organizacion_id)
    nacional = organizacion.cobertura_nacional if cobertura_nacional is None else cobertura_nacional
    zonas_normalizadas = _resolver_cobertura(organizacion.tipo, normalizar_zonas(zonas), nacional)

    organizacion.contacto_email = _normalizar_texto(contacto_email)
    organizacion.contacto_telefono = _normalizar_texto(contacto_telefono)
    organizacion.direccion = _normalizar_texto(direccion)
    organizacion.cobertura_nacional = nacional
    _reemplazar_zonas(organizacion, zonas_normalizadas)
    db.session.commit()

    registrar_evento(
        logging.INFO,
        "organizacion_editada_por_miembro",
        id_organizacion=str(organizacion.id),
        id_correlacion=id_correlacion_actual(),
    )
    return organizacion


def cambiar_estado(organizacion_id: int, *, activo: bool) -> Organizacion:
    """Alta o baja logica.

    No se borra nunca: las emergencias, ofertas y adjudicaciones ya registradas apuntan a la
    organizacion, y perderlas dejaria el historial del proceso incompleto.

    Tampoco se tocan las cuentas: mientras la organizacion este inactiva, sus miembros no pueden
    ingresar ni seguir operando (lo resuelve `usuarios_roles.servicios` consultando
    `esta_activa()`), y al reactivarla recuperan el acceso sin que haya que rehabilitarlas una
    por una.
    """
    organizacion = obtener(organizacion_id)
    organizacion.activo = activo
    db.session.commit()

    registrar_evento(
        logging.INFO,
        "organizacion_cambio_de_estado",
        id_organizacion=str(organizacion.id),
        activo=activo,
        id_correlacion=id_correlacion_actual(),
    )
    return organizacion


def registrar_resultado_de_verificacion(
    organizacion_id: int, estado: str | EstadoVerificacion
) -> Organizacion:
    """Guarda el resultado de la validacion contra el Sistema Nacional.

    Punto de extension para la integracion con la API Nacional, por si informa un resultado
    distinto del que la organizacion trajo al cargarse. Ninguna pantalla la expone.
    """
    organizacion = obtener(organizacion_id)
    organizacion.estado_verificacion = convertir_estado_verificacion(estado)
    db.session.commit()

    registrar_evento(
        logging.INFO,
        "organizacion_verificacion_registrada",
        id_organizacion=str(organizacion.id),
        estado=organizacion.estado_verificacion.value,
        id_correlacion=id_correlacion_actual(),
    )
    return organizacion


def miembros(organizacion_id: int) -> list[dict[str, Any]]:
    """Cuentas vinculadas a la organizacion, activas e inactivas, ordenadas por nombre.

    Se leen por la relacion `Organizacion.usuarios` para no importar `usuarios_roles`, que esta
    despues en la cadena de dependencias.
    """
    organizacion = obtener(organizacion_id)
    cuentas = sorted(organizacion.usuarios, key=lambda cuenta: (cuenta.nombre_completo, cuenta.id))
    return [
        {
            "id": cuenta.id,
            "nombre_completo": cuenta.nombre_completo,
            "email": cuenta.email,
            "roles": sorted(rol.nombre for rol in cuenta.roles),
            "activo": cuenta.activo,
        }
        for cuenta in cuentas
    ]


def zona_a_diccionario(zona: ZonaDeCobertura) -> dict[str, Any]:
    """Representacion de una zona de cobertura."""
    return {"provincia": zona.provincia, "localidad": zona.localidad}


def a_diccionario(organizacion: Organizacion) -> dict[str, Any]:
    """Representacion de la organizacion para la respuesta HTTP.

    Es tambien lo que la plantilla recibe como contexto: la vista no cambia segun el formato de
    salida.
    """
    return {
        "id": organizacion.id,
        "nombre": organizacion.nombre,
        "tipo": organizacion.tipo.value,
        "identificador_nacional": organizacion.identificador_nacional,
        "contacto_email": organizacion.contacto_email,
        "contacto_telefono": organizacion.contacto_telefono,
        "direccion": organizacion.direccion,
        "cobertura_nacional": organizacion.cobertura_nacional,
        "zonas_de_cobertura": [
            zona_a_diccionario(zona) for zona in organizacion.zonas_de_cobertura
        ],
        "activo": organizacion.activo,
        "estado_verificacion": organizacion.estado_verificacion.value,
        "creado_en": organizacion.creado_en.isoformat() if organizacion.creado_en else None,
        "actualizado_en": (
            organizacion.actualizado_en.isoformat() if organizacion.actualizado_en else None
        ),
    }
