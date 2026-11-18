"""usa UUID como clave primaria de todas las entidades

Revision ID: 9e4b7c1d2a53
Revises: 45558706fd3d
Create Date: 2026-11-16 20:00:00.000000

Con ids enteros, cada aplicación web local numeraba sus emergencias desde 1, y como todas usan
la misma API del Sistema Nacional, la emergencia 1 de un integrante pisaba los compromisos de la
emergencia 1 de otro (ver app/core/identificadores.py). Esta migración pasa a UUID la clave
primaria de cada tabla y todas las claves foráneas que la apuntan, sin perder datos:

1. Suelta las claves foráneas que apuntan a las tablas convertidas.
2. Agrega a cada tabla una columna UUID y la llena con UUIDv7 en el orden de los ids viejos, así
   ordenar por id sigue dando el orden de alta.
3. Agrega una columna UUID por cada clave foránea y la llena cruzando con el id viejo del padre.
4. Borra las columnas enteras (PostgreSQL arrastra la clave primaria, los únicos, los índices y
   las secuencias que dependen de ellas) y renombra las nuevas.
5. Vuelve a crear la clave primaria, los únicos, los índices y las foráneas con el mismo nombre,
   el mismo ON DELETE y la misma nulabilidad que tenían.
6. Traduce los ids guardados como texto: el `enlace` de las notificaciones (`/emergencias/3`) y
   el JSON del historial de ofertas (`oferta_version.items_snapshot`).

El downgrade hace el camino inverso: numera las filas desde 1 en el orden de su UUID, les vuelve
a poner una secuencia y traduce los textos de vuelta. Los ids enteros que salen no son los
originales.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict
from collections.abc import Callable

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "9e4b7c1d2a53"
down_revision = "45558706fd3d"
branch_labels = None
depends_on = None

SUFIJO = "__nuevo"

# Todas las tablas con columna `id`. Las de asociación (oferta_organizacion, usuario_rol,
# rol_permiso) no tienen id propio: sus columnas se convierten por ser claves foráneas.
TABLAS = (
    "organizacion",
    "organizacion_zona_cobertura",
    "inventario",
    "inventario_item",
    "item",
    "permisos",
    "roles",
    "usuarios",
    "emergencia",
    "convocatoria",
    "lote_necesidad",
    "lote_item",
    "oferta",
    "oferta_item",
    "oferta_version",
    "ejecucion_tarea",
    "notificacion",
)

# Segmento de una ruta de la web -> tabla del id que lo sigue. Sirve para traducir los enlaces
# de las notificaciones: /emergencias/3, /adjudicaciones/convocatoria/5, /ofertas/7, etc.
TABLA_POR_SEGMENTO = {
    "emergencias": "emergencia",
    "convocatorias": "convocatoria",
    "convocatoria": "convocatoria",
    "ofertas": "oferta",
    "organizaciones": "organizacion",
    "usuarios": "usuarios",
    "lotes": "lote_necesidad",
    "tareas": "ejecucion_tarea",
    "notificaciones": "notificacion",
}


def _uuid7(_fila, _orden: int) -> uuid.UUID:
    return uuid.uuid7()


def _entero(_fila, orden: int) -> int:
    return orden


def _cambiar_claves(
    generadores: dict[str, Callable],
    tipo_de: Callable[[str], sa.types.TypeEngine],
) -> dict[str, dict[str, object]]:
    """Cambia el tipo de `id` de cada tabla de `generadores` y de las foráneas que lo apuntan.

    Devuelve, por tabla, el id nuevo de cada id viejo (con el viejo como texto), para traducir
    los ids guardados fuera de las claves foráneas.
    """
    conexion = op.get_bind()
    if conexion.dialect.name != "postgresql":
        raise RuntimeError("Esta migración solo corre sobre PostgreSQL.")
    inspector = sa.inspect(conexion)
    tablas = set(generadores)

    foraneas = []
    for tabla in inspector.get_table_names():
        for foranea in inspector.get_foreign_keys(tabla):
            if foranea["referred_table"] not in tablas:
                continue
            if foranea["referred_columns"] != ["id"] or len(foranea["constrained_columns"]) != 1:
                raise RuntimeError(f"Clave foránea no soportada en {tabla}: {foranea['name']}")
            foraneas.append((tabla, foranea))

    afectadas: dict[str, set[str]] = defaultdict(set)
    for tabla in tablas:
        afectadas[tabla].add("id")
    for tabla, foranea in foraneas:
        afectadas[tabla].add(foranea["constrained_columns"][0])

    columnas = {
        tabla: {columna["name"]: columna for columna in inspector.get_columns(tabla)}
        for tabla in afectadas
    }
    primarias, unicos, indices = {}, [], []
    for tabla, nombres in afectadas.items():
        primaria = inspector.get_pk_constraint(tabla)
        if set(primaria["constrained_columns"]) & nombres:
            primarias[tabla] = primaria
        for unico in inspector.get_unique_constraints(tabla):
            if set(unico["column_names"]) & nombres:
                unicos.append((tabla, unico))
        for indice in inspector.get_indexes(tabla):
            if not indice.get("duplicates_constraint") and set(indice["column_names"]) & nombres:
                indices.append((tabla, indice))

    # 1. Foráneas afuera, para poder cambiar las columnas de los dos lados.
    for tabla, foranea in foraneas:
        op.drop_constraint(foranea["name"], tabla, type_="foreignkey")

    # 2. Clave primaria nueva de cada tabla, en el orden de la clave vieja.
    mapas: dict[str, dict[str, object]] = {}
    for tabla, generar in generadores.items():
        op.add_column(tabla, sa.Column(f"id{SUFIJO}", tipo_de(tabla), nullable=True))
        filas = conexion.execute(sa.text(f'SELECT * FROM "{tabla}" ORDER BY id')).all()
        valores = [
            {"viejo": fila.id, "nuevo": generar(fila, orden)}
            for orden, fila in enumerate(filas, start=1)
        ]
        if valores:
            conexion.execute(
                sa.text(f'UPDATE "{tabla}" SET "id{SUFIJO}" = :nuevo WHERE id = :viejo'),
                valores,
            )
        mapas[tabla] = {str(valor["viejo"]): valor["nuevo"] for valor in valores}

    # 3. Foránea nueva de cada hija, cruzando con la clave vieja del padre.
    for tabla, foranea in foraneas:
        columna = foranea["constrained_columns"][0]
        padre = foranea["referred_table"]
        op.add_column(tabla, sa.Column(f"{columna}{SUFIJO}", tipo_de(padre), nullable=True))
        conexion.execute(
            sa.text(
                f'UPDATE "{tabla}" AS hija SET "{columna}{SUFIJO}" = padre."id{SUFIJO}" '
                f'FROM "{padre}" AS padre WHERE padre.id = hija."{columna}"'
            )
        )

    # 4. Columnas viejas afuera (se llevan la clave primaria, los únicos, los índices y las
    # secuencias que dependen de ellas) y las nuevas toman su nombre.
    for tabla, nombres in afectadas.items():
        for nombre in sorted(nombres):
            op.drop_column(tabla, nombre)
        for nombre in sorted(nombres):
            original = columnas[tabla][nombre]
            op.alter_column(
                tabla,
                f"{nombre}{SUFIJO}",
                new_column_name=nombre,
                nullable=original["nullable"],
            )
            if original.get("comment"):
                op.alter_column(tabla, nombre, comment=original["comment"])

    # 5. Restricciones de vuelta, con el mismo nombre que tenían.
    for tabla, primaria in primarias.items():
        op.create_primary_key(primaria["name"], tabla, primaria["constrained_columns"])
    for tabla, unico in unicos:
        op.create_unique_constraint(unico["name"], tabla, unico["column_names"])
    for tabla, indice in indices:
        op.create_index(indice["name"], tabla, indice["column_names"], unique=indice["unique"])
    for tabla, foranea in foraneas:
        opciones = foranea.get("options") or {}
        op.create_foreign_key(
            foranea["name"],
            tabla,
            foranea["referred_table"],
            foranea["constrained_columns"],
            foranea["referred_columns"],
            ondelete=opciones.get("ondelete"),
            onupdate=opciones.get("onupdate"),
        )
    return mapas


def _traducir(mapas: dict[str, dict[str, object]], tabla: str, valor: object) -> object | None:
    """El id nuevo de `valor` en `tabla`, o None si no estaba (se deja el texto como está)."""
    return mapas.get(tabla, {}).get(str(valor))


def _traducir_enlace(mapas: dict[str, dict[str, object]], enlace: str) -> str:
    """Traduce cada id de una ruta según el segmento que lo precede (/ofertas/7 -> oferta 7)."""
    camino, separador, resto = enlace.partition("?")
    segmentos = camino.split("/")
    for posicion in range(1, len(segmentos)):
        tabla = TABLA_POR_SEGMENTO.get(segmentos[posicion - 1])
        nuevo = _traducir(mapas, tabla, segmentos[posicion]) if tabla else None
        if nuevo is not None:
            segmentos[posicion] = str(nuevo)
    return "/".join(segmentos) + separador + resto


def _para_json(valor: object) -> object:
    return str(valor) if isinstance(valor, uuid.UUID) else valor


def _traducir_snapshot(mapas: dict[str, dict[str, object]], texto: str) -> str:
    """Traduce los ids del JSON con las líneas de una versión anterior de la oferta."""
    try:
        lineas = json.loads(texto)
    except TypeError, ValueError:
        return texto
    if not isinstance(lineas, list):
        return texto
    for linea in lineas:
        if not isinstance(linea, dict):
            continue
        for clave, tabla in (("id", "oferta_item"), ("lote_item_id", "lote_item")):
            nuevo = _traducir(mapas, tabla, linea.get(clave))
            if nuevo is not None:
                linea[clave] = _para_json(nuevo)
        recurso = linea.get("recurso")
        if isinstance(recurso, dict):
            nuevo = _traducir(mapas, "item", recurso.get("item_id"))
            if nuevo is not None:
                recurso["item_id"] = _para_json(nuevo)
    return json.dumps(lineas, ensure_ascii=False)


def _traducir_textos(mapas: dict[str, dict[str, object]]) -> None:
    conexion = op.get_bind()
    enlaces = [
        {"id": fila.id, "enlace": _traducir_enlace(mapas, fila.enlace)}
        for fila in conexion.execute(sa.text("SELECT id, enlace FROM notificacion")).all()
    ]
    if enlaces:
        conexion.execute(
            sa.text("UPDATE notificacion SET enlace = :enlace WHERE id = :id"), enlaces
        )
    snapshots = [
        {"id": fila.id, "items_snapshot": _traducir_snapshot(mapas, fila.items_snapshot)}
        for fila in conexion.execute(sa.text("SELECT id, items_snapshot FROM oferta_version")).all()
    ]
    if snapshots:
        conexion.execute(
            sa.text("UPDATE oferta_version SET items_snapshot = :items_snapshot WHERE id = :id"),
            snapshots,
        )


def upgrade():
    mapas = _cambiar_claves(dict.fromkeys(TABLAS, _uuid7), lambda _tabla: sa.Uuid())
    _traducir_textos(mapas)


def downgrade():
    mapas = _cambiar_claves(dict.fromkeys(TABLAS, _entero), lambda _tabla: sa.Integer())
    conexion = op.get_bind()
    for tabla in TABLAS:
        secuencia = f"{tabla}_id_seq"
        conexion.execute(sa.text(f'CREATE SEQUENCE "{secuencia}" AS integer OWNED BY "{tabla}".id'))
        conexion.execute(
            sa.text(f"ALTER TABLE \"{tabla}\" ALTER COLUMN id SET DEFAULT nextval('{secuencia}')")
        )
        conexion.execute(
            sa.text(
                f"SELECT setval('{secuencia}', COALESCE((SELECT max(id) FROM \"{tabla}\"), 0) + 1,"
                " false)"
            )
        )
    _traducir_textos(mapas)
