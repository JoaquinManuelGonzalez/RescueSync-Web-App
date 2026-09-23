"""Datos semilla de organizaciones para el entorno de demostración."""

from __future__ import annotations

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.modulos.organizaciones.modelos import Organizacion, TipoOrganizacion

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
