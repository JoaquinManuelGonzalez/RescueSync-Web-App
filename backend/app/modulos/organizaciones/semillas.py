"""Datos semilla para el módulo de organizaciones (municipios, centros coordinadores y ONGs)."""

from __future__ import annotations

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.modulos.organizaciones.modelos import Organizacion, TipoOrganizacion

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
