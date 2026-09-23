"""Datos semilla para el módulo de organizaciones (municipios, centros coordinadores y ONGs)."""

from __future__ import annotations

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.modulos.emergencias.modelos import Item
from app.modulos.organizaciones.modelos import (
    Inventario,
    InventarioItem,
    Organizacion,
    TipoOrganizacion,
)

# # # # # # # # # # # # Organizaciones # # # # # # # # # # # #
ORGANIZACIONES: list[dict] = [
    {
        "nombre": "Municipalidad de Bahía Blanca",
        "tipo": TipoOrganizacion.municipio,
        "identificador_nacional": "30-99999999-1",
        "contacto_email": "bahiablanca@test.gob.ar",
        "contacto_telefono": "+54 291 555-0001",
        "direccion": "Av. Colón 1, Bahía Blanca, Buenos Aires",
    },
    {
        "nombre": "Municipalidad de La Plata",
        "tipo": TipoOrganizacion.municipio,
        "identificador_nacional": "30-99999999-2",
        "contacto_email": "laplata@test.gob.ar",
        "contacto_telefono": "+54 221 555-0002",
        "direccion": "Calle 12 y 51, La Plata, Buenos Aires",
    },
    {
        "nombre": "Municipalidad de Pergamino",
        "tipo": TipoOrganizacion.municipio,
        "identificador_nacional": "30-99999999-3",
        "contacto_email": "pergamino@test.gob.ar",
        "contacto_telefono": "+54 247 732-8000",
        "direccion": "Florida 629, Pergamino, Buenos Aires",
    },
    {
        "nombre": "Cruz Roja Argentina - Filial Bahía Blanca",
        "tipo": TipoOrganizacion.ong,
        "identificador_nacional": "30-99999999-4",
        "contacto_email": "cruzroja.bahiablanca@test.org.ar",
        "contacto_telefono": "+54 291 555-0003",
        "direccion": "Zelarrayán 100, Bahía Blanca, Buenos Aires",
    },
    {
        "nombre": "Bomberos Voluntarios de La Plata",
        "tipo": TipoOrganizacion.ong,
        "identificador_nacional": "30-99999999-5",
        "contacto_email": "bomberos.laplata@test.org.ar",
        "contacto_telefono": "+54 221 555-0004",
        "direccion": "Calle 60 y 120, La Plata, Buenos Aires",
    },
    {
        "nombre": "Grupo Scouts de Pergamino",
        "tipo": TipoOrganizacion.ong,
        "identificador_nacional": "30-99999999-6",
        "contacto_email": "scouts.pergamino@test.org.ar",
        "contacto_telefono": "+54 247 732-8989",
        "direccion": "Maipú 602, Pergamino, Buenos Aires",
    },
    {
        "nombre": "Centro Coordinador Regional de la Provincia Buenos Aires",
        "tipo": TipoOrganizacion.centro_coordinador_regional,
        "identificador_nacional": "30-99999999-7",
        "contacto_email": "coordinacion.bsas@rescuesync.test",
        "contacto_telefono": "+54 11 555-0005",
        "direccion": "Calle 6 y 53, La Plata, Buenos Aires",
    },
]


@registrar("organizaciones")
def sembrar_organizaciones() -> list[ResultadoSemilla]:

    resultado = ResultadoSemilla("organizaciones")

    for datos in ORGANIZACIONES:
        nombre = datos["nombre"]
        valores = {k: v for k, v in datos.items() if k != "nombre"}
        _, creado = obtener_o_crear(
            Organizacion,
            claves={"nombre": nombre},
            valores=valores,
        )
        resultado.contar(creado)

    return [resultado]


# # # # # # # # # # # # Inventarios # # # # # # # # # # # #
# Los nombres de ítems deben existir en emergencias/semillas.py::ITEMS.
# Sólo las ONGs tienen inventarios
INVENTARIOS: dict[str, dict] = {
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
      - InventarioItem: Si ya existe, NO se actualiza la cantidad.
    """
    resultado = ResultadoSemilla("inventarios")

    for nombre_org, config in INVENTARIOS.items():
        organizacion = Organizacion.query.filter_by(nombre=nombre_org).first()
        if organizacion is None:
            raise ValueError(
                f"Organización no encontrada para inventario: {nombre_org!r}. "
                f"Revisar si está declarada en organizaciones/semillas.py::ORGANIZACIONES"
            )

        inventario, creado = obtener_o_crear(
            Inventario,
            claves={"organizacion_id": organizacion.id},
            valores={
                "nombre": config["inventario"]["nombre"],
                "descripcion": config["inventario"]["descripcion"],
            },
        )
        resultado.contar(creado)

        for nombre_item, cantidad in config["stock"].items():
            item = Item.query.filter_by(nombre=nombre_item).first()
            if item is None:
                raise ValueError(
                    f"Item no encontrado en el catálogo: {nombre_item!r}. "
                    f"Revisar si está declarado en emergencias/semillas.py::ITEMS"
                )
            _, fue_creado = obtener_o_crear(
                InventarioItem,
                claves={
                    "inventario_id": inventario.id,
                    "item_id": item.id,
                },
                valores={"cantidad_disponible": cantidad},
            )
    return [resultado]
