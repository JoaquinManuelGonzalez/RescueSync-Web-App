"""Datos semilla de organizaciones para el entorno de demostración."""

from __future__ import annotations

from sqlalchemy import select

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.extensiones import db
from app.modulos.emergencias.modelos import Item
from app.modulos.organizaciones.modelos import (
    Inventario,
    InventarioItem,
    Organizacion,
    TipoOrganizacion,
)

ORGANIZACIONES: list[dict] = [
    {
        "nombre": "Municipio de Chascomús",
        "tipo": TipoOrganizacion.municipio,
        "identificador_nacional": "30-71234567-9",
        "activo": True,
    },
    {
        "nombre": "Centro Coordinador Regional Buenos Aires",
        "tipo": TipoOrganizacion.centro_coordinador_regional,
        "identificador_nacional": "30-70987654-3",
        "activo": True,
    },
    {
        "nombre": "Cruz Solidaria",
        "tipo": TipoOrganizacion.ong,
        "identificador_nacional": "30-65432198-7",
        "activo": True,
    },
    {
        "nombre": "Manos Unidas",
        "tipo": TipoOrganizacion.ong,
        "identificador_nacional": "30-65432199-5",
        "activo": True,
    },
]

INVENTARIOS: dict[str, dict] = {
    "Municipio de Chascomús": {
        "nombre": "Depósito municipal",
        "descripcion": "Recursos disponibles para respuesta local.",
        "items": {
            "Agua potable envasada": 500,
            "Raciones de alimento no perecedero": 250,
            "Frazadas": 100,
        },
    },
    "Centro Coordinador Regional Buenos Aires": {
        "nombre": "Centro regional de distribución",
        "descripcion": "Recursos coordinados para emergencias regionales.",
        "items": {
            "Paramédicos": 20,
            "Agua potable envasada": 1000,
            "Generadores eléctricos": 5,
        },
    },
    "Cruz Solidaria": {
        "nombre": "Depósito Cruz Solidaria",
        "descripcion": "Donaciones listas para distribución humanitaria.",
        "items": {
            "Raciones de alimento no perecedero": 600,
            "Botiquines de primeros auxilios": 80,
            "Carpas familiares": 25,
        },
    },
    "Manos Unidas": {
        "nombre": "Depósito Manos Unidas",
        "descripcion": "Stock de apoyo para operativos de asistencia.",
        "items": {
            "Agua potable envasada": 400,
            "Frazadas": 150,
            "Colchones": 40,
        },
    },
}


@registrar("organizaciones")
def sembrar_organizaciones() -> list[ResultadoSemilla]:

    resultado = ResultadoSemilla("organizaciones")

    for datos in ORGANIZACIONES:
        nombre = datos["nombre"]
        valores = {k: v for k, v in datos.items() if k != "nombre"}
        organizacion, creado = obtener_o_crear(
            Organizacion,
            claves={"nombre": nombre},
            valores=valores,
        )
        resultado.contar(creado)

        datos_inventario = INVENTARIOS[nombre]
        inventario, creado = obtener_o_crear(
            Inventario,
            claves={"organizacion_id": organizacion.id},
            valores={
                "nombre": datos_inventario["nombre"],
                "descripcion": datos_inventario["descripcion"],
            },
        )
        resultado.contar(creado)

        for nombre_item, cantidad in datos_inventario["items"].items():
            item = db.session.execute(select(Item).where(Item.nombre == nombre_item)).scalar_one()
            _, creado = obtener_o_crear(
                InventarioItem,
                claves={"inventario_id": inventario.id, "item_id": item.id},
                valores={"cantidad_disponible": cantidad},
            )
            resultado.contar(creado)

    return [resultado]
