"""Datos semilla de organizaciones.

Carga las organizaciones minimas para poder recorrer el proceso de punta a punta: el municipio
que registra la emergencia, el centro coordinador que arma los lotes y dos ONGs, que son dos y
no una para que se pueda probar tambien el caso de consorcio del enunciado.

Es idempotente: identifica cada fila por su nombre, que es la clave natural, y no hace commit
(de eso se ocupa `flask seed`, que envuelve toda la carga en una unica transaccion).
"""

from __future__ import annotations

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.modulos.organizaciones.modelos import Organizacion, TipoOrganizacion

ORGANIZACIONES_DE_DEMOSTRACION: tuple[tuple[str, TipoOrganizacion, str], ...] = (
    ("Municipio de Chascomús", TipoOrganizacion.municipio, "30-71234567-9"),
    (
        "Centro Coordinador Regional Buenos Aires",
        TipoOrganizacion.centro_coordinador_regional,
        "30-70987654-3",
    ),
    ("Cruz Solidaria", TipoOrganizacion.ong, "30-65432198-7"),
    ("Manos Unidas", TipoOrganizacion.ong, "30-65432199-5"),
)


@registrar("organizaciones")
def sembrar_organizaciones() -> list[ResultadoSemilla]:
    """Crea el municipio, el centro coordinador y las dos ONGs de demostración."""
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
