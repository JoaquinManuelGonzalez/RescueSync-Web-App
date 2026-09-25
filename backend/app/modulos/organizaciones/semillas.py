"""Datos semilla de organizaciones.

Carga las organizaciones mínimas para poder recorrer el proceso de punta a punta:
los municipios que registran emergencias, el centro coordinador que arma los
lotes, y las ONGs que presentan ofertas de ayuda. Se incluyen varias ONGs para
poder probar también el caso de consorcio del enunciado.

Es idempotente: identifica cada fila por su nombre, que es la clave natural, y no hace commit
(de eso se ocupa `flask seed`, que envuelve toda la carga en una unica transaccion).
"""

from __future__ import annotations

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.modulos.emergencias.modelos import Item
from app.modulos.organizaciones.modelos import (
    Inventario,
    InventarioItem,
    Organizacion,
    TipoOrganizacion,
    ZonaDeCobertura,
)

# # # # # # # # # # # # Organizaciones # # # # # # # # # # # #
# Formato: (nombre, tipo, identificador_nacional).
# El orden importa:
#     * Los municipios primero (los necesitan los seeders de emergencias)
#     * Luego el centro coordinador
#     * Por último las ONGs.

ORGANIZACIONES_DE_DEMOSTRACION: tuple[tuple[str, TipoOrganizacion, str], ...] = (
    # --- Municipios ---
    (
        "Municipio de Chascomús",
        TipoOrganizacion.municipio,
        "30-71234567-9"
    ),
    (
        "Municipalidad de Bahía Blanca",
        TipoOrganizacion.municipio,
        "30-99999999-1"
    ),
    (
        "Municipalidad de La Plata",
        TipoOrganizacion.municipio,
        "30-99999999-2"
    ),
    (
        "Municipalidad de Pergamino",
        TipoOrganizacion.municipio,
        "30-99999999-3"
    ),
    # --- Centro coordinador regional ---
    (
        "Centro Coordinador Regional Buenos Aires",
        TipoOrganizacion.centro_coordinador_regional,
        "30-70987654-3",
    ),
    # --- ONGs ---
    (
        "Cruz Solidaria",
        TipoOrganizacion.ong,
        "30-65432198-7"
    ),
    (
        "Manos Unidas",
        TipoOrganizacion.ong,
        "30-65432199-5"
    ),
    (
        "Cruz Roja Argentina - Filial Bahía Blanca",
        TipoOrganizacion.ong,
        "30-99999999-4",
    ),
    (
        "Bomberos Voluntarios de La Plata",
        TipoOrganizacion.ong,
        "30-99999999-5",
    ),
    (
        "Grupo Scouts de Pergamino",
        TipoOrganizacion.ong,
        "30-99999999-6"
    ),
)


@registrar("organizaciones")
def sembrar_organizaciones() -> list[ResultadoSemilla]:
    """Crea los municipios, el centro coordinador y las ONGs de demostración."""
    resultado = ResultadoSemilla("organizaciones")

    for nombre, tipo, identificador in ORGANIZACIONES_DE_DEMOSTRACION:
        _, fue_creada = obtener_o_crear(
            Organizacion,
            claves={"nombre": nombre},
            valores={
                "tipo": tipo,
                "identificador_nacional": identificador,
                "activo": True,
            },
        )
        resultado.contar(fue_creada)

    return [resultado]


# # # # # # # # # # # # Zonas de cobertura # # # # # # # # # # # #
# Formato: nombre de la organizacion -> [(provincia, localidad)]. Localidad None = toda la
# provincia. Toda ONG declara al menos una zona, como exige `servicios.crear()`.

ZONAS_DE_COBERTURA: dict[str, list[tuple[str, str | None]]] = {
    "Municipio de Chascomús": [("Buenos Aires", "Chascomús")],
    "Municipalidad de Bahía Blanca": [("Buenos Aires", "Bahía Blanca")],
    "Municipalidad de La Plata": [("Buenos Aires", "La Plata")],
    "Municipalidad de Pergamino": [("Buenos Aires", "Pergamino")],
    "Centro Coordinador Regional Buenos Aires": [("Buenos Aires", None)],
    "Cruz Solidaria": [
        ("Buenos Aires", "Chascomús"),
        ("Buenos Aires", "La Plata"),
        ("Ciudad Autónoma de Buenos Aires", None),
    ],
    "Manos Unidas": [("Buenos Aires", "Chascomús")],
    "Cruz Roja Argentina - Filial Bahía Blanca": [
        ("Buenos Aires", "Bahía Blanca"),
        ("Buenos Aires", "Coronel Rosales"),
        ("Buenos Aires", "Villarino"),
    ],
    "Bomberos Voluntarios de La Plata": [
        ("Buenos Aires", "Berisso"),
        ("Buenos Aires", "Ensenada"),
        ("Buenos Aires", "La Plata"),
    ],
    "Grupo Scouts de Pergamino": [("Buenos Aires", "Pergamino")],
}


@registrar("zonas_de_cobertura")
def sembrar_zonas_de_cobertura() -> list[ResultadoSemilla]:
    """Declara la zona de cobertura de cada organización de demostración."""
    resultado = ResultadoSemilla("zonas_de_cobertura")

    for nombre_org, zonas in ZONAS_DE_COBERTURA.items():
        organizacion = Organizacion.query.filter_by(nombre=nombre_org).first()
        if organizacion is None:
            raise ValueError(
                f"Organización no encontrada para zona de cobertura: {nombre_org!r}. "
                f"Revisar si está declarada en: "
                f"organizaciones/semillas.py::ORGANIZACIONES_DE_DEMOSTRACION"
            )
        for provincia, localidad in zonas:
            _, fue_creada = obtener_o_crear(
                ZonaDeCobertura,
                claves={
                    "organizacion_id": organizacion.id,
                    "provincia": provincia,
                    "localidad": localidad,
                },
            )
            resultado.contar(fue_creada)

    return [resultado]


# # # # # # # # # # # # Inventarios # # # # # # # # # # # #
# * Los nombres de ítems deben existir en emergencias/semillas_items.py::ITEMS.
# * Sólo las ONGs tienen inventarios.
#
# `Manos Unidas` aún no tiene inventario.
# Cruz Solidaria tiene stock demo porque es la ONG utilizada para probar ofertas.

INVENTARIOS: dict[str, dict] = {
    "Cruz Solidaria": {
        "inventario": {
            "nombre": "Depósito Cruz Solidaria",
            "descripcion": "Stock demo para ofertas de ayuda.",
        },
        "stock": {
            "Agua potable envasada": 1000,
            "Paramédicos": 10,
            "Raciones de alimento no perecedero": 600,
        },
    },
    "Cruz Roja Argentina - Filial Bahía Blanca": {
        "inventario": {
            "nombre": "Depósito Cruz Roja Bahía Blanca",
            "descripcion": "Centro logístico de la filial.",
        },
        "stock": {
            "Paramédicos": 15,
            "Enfermeros": 8,
            "Botiquines de primeros auxilios": 40,
            "Frazadas": 200,
            "Agua potable envasada": 1000,
            "Suplemento alimenticio": 1000,
            "Antibióticos": 30000,
            "Analgésicos": 50000,
            "Ambulancias": 5,
            "Camiones de carga": 1,
            "Suero fisiológico": 500,
            "Pañales para adulto": 400,
            "Ibuprofeno": 5000,
            "Paracetamol": 5000,
            "Raciones de alimento no perecedero": 400,
            "Leche en polvo": 590,
            "Toallas jabonosas": 1500,
            "Kit higiene bucal": 500,
        },
    },
    "Bomberos Voluntarios de La Plata": {
        "inventario": {
            "nombre": "Cuartel central La Plata",
            "descripcion": "Stock del cuartel de bomberos voluntarios.",
        },
        "stock": {
            "Rescatistas": 25,
            "Perros de búsqueda": 3,
            "Retroexcavadoras": 1,
            "Camiones de carga": 2,
            "Ambulancias": 1,
            "Frazadas": 100,
            "Colchones": 120,
            "Agua potable envasada": 3000,
            "Botiquines de primeros auxilios": 60,
            "Generadores eléctricos": 4,
            "Tanques de agua": 12,
        },
    },
    "Grupo Scouts de Pergamino": {
        "inventario": {
            "nombre": "Depósito Scouts Pergamino",
            "descripcion": "Acopio de campaña del grupo scout.",
        },
        "stock": {
            "Voluntarios generales": 40,
            "Carpas familiares": 10,
            "Colchones": 30,
            "Pañales para bebes": 50,
            "Leche en polvo": 80,
            "Toallas jabonosas": 100,
            "Yerba": 1000,
            "Botiquines de primeros auxilios": 50,
            "Lentejas": 30,
            "Harina de trigo": 50,
            "Fideos": 50,
            "Arroz": 25,
            "Café": 20,
            "Latas de arvejas": 100,
            "Frazadas": 800,
            "Agua potable envasada": 5000,
            "Raciones de alimento no perecedero": 1200,
            "Kit higiene bucal": 250,
            "Suplemento alimenticio": 20,
            "Antibióticos": 3000,
            "Analgésicos": 5000,
        },
    },
}


@registrar("inventarios")
def sembrar_inventarios() -> list[ResultadoSemilla]:
    """Crea un inventario por organización y le carga stock inicial.
    Notas:
      - Inventario: clave natural `organizacion_id` (unique=True en el modelo).
      - InventarioItem: si ya existe, NO se actualiza la cantidad. El stock es
        dato operativo que muta con la aplicación, no con la semilla.
    """
    resultado_inv = ResultadoSemilla("inventarios")
    resultado_items = ResultadoSemilla("inventario_items")

    for nombre_org, config in INVENTARIOS.items():
        organizacion = Organizacion.query.filter_by(nombre=nombre_org).first()
        if organizacion is None:
            raise ValueError(
                f"Organización no encontrada para inventario: {nombre_org!r}. "
                f"Revisar si está declarada en: "
                f"organizaciones/semillas.py::ORGANIZACIONES_DE_DEMOSTRACION"
            )

        inventario, creado = obtener_o_crear(
            Inventario,
            claves={"organizacion_id": organizacion.id},
            valores={
                "nombre": config["inventario"]["nombre"],
                "descripcion": config["inventario"]["descripcion"],
            },
        )
        resultado_inv.contar(creado)

        for nombre_item, cantidad in config["stock"].items():
            item = Item.query.filter_by(nombre=nombre_item).first()
            if item is None:
                raise ValueError(
                    f"Item no encontrado en el catálogo: {nombre_item!r}. "
                    f"Revisar si está declarado en: "
                    f"emergencias/semillas_items.py::ITEMS"
                )
            _, fue_creado = obtener_o_crear(
                InventarioItem,
                claves={
                    "inventario_id": inventario.id,
                    "item_id": item.id,
                },
                valores={"cantidad_disponible": cantidad},
            )
            resultado_items.contar(fue_creado)

    return [resultado_inv, resultado_items]
