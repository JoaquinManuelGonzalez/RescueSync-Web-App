"""Identificadores de las entidades de RescueSync.

Todas las claves primarias son UUID. Con ids enteros, cada aplicación web local numeraba sus
emergencias desde 1, y como todas usan la misma API del Sistema Nacional, la emergencia 1 de un
integrante pisaba los compromisos de la emergencia 1 de otro. Un UUID no se repite entre
entornos, así que el id que viaja a Bonita y a la API sirve como clave en cualquiera de ellos.

Las filas nuevas usan UUIDv7: llevan la hora al principio, así que ordenar por `id` sigue siendo
ordenar por fecha de alta, y los índices crecen al final como con un entero.
"""

from __future__ import annotations

import uuid


def nuevo_id() -> uuid.UUID:
    """Id para una fila nueva: UUIDv7, ordenable por fecha de alta."""
    return uuid.uuid7()


def parsear_id(valor: object) -> uuid.UUID | None:
    """Convierte un id recibido (formulario, JSON o Bonita) en UUID, o None si no es válido.

    Acepta el UUID ya parseado o su texto, con o sin guiones y en mayúsculas o minúsculas.
    Cualquier otra cosa (un entero, un texto vacío) devuelve None para que quien llama responda
    con su propio error.
    """
    if isinstance(valor, uuid.UUID):
        return valor
    if not isinstance(valor, str):
        return None
    try:
        return uuid.UUID(valor.strip())
    except ValueError:
        return None


def exigir_id(valor: object) -> uuid.UUID:
    """Como `parsear_id`, pero levanta ValueError si el valor no es un UUID.

    Es la forma que esperan las conversiones de WTForms (`coerce` de un SelectField): un
    ValueError ahí se convierte en un error de validación del campo.
    """
    identificador = parsear_id(valor)
    if identificador is None:
        raise ValueError("No es un identificador válido.")
    return identificador
