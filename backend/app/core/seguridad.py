"""Primitivas de seguridad compartidas.

El hasheo de contrasenas se centraliza aca para que nadie tenga que elegir un algoritmo al
escribir un modelo, un formulario o un seeder
"""

from __future__ import annotations

import re

from werkzeug.security import check_password_hash, generate_password_hash

# scrypt es el algoritmo por defecto de Werkzeug 3 y no necesita dependencias extra.
METODO_HASH = "scrypt"


def hashear_contrasena(contrasena: str) -> str:
    """Devuelve el hash a guardar en la base. La contrasena en claro nunca se persiste."""
    return generate_password_hash(contrasena, method=METODO_HASH)


def verificar_contrasena(hash_almacenado: str, contrasena: str) -> bool:
    """Compara una contrasena en claro contra el hash guardado, en tiempo constante."""
    return check_password_hash(hash_almacenado, contrasena)


# Verificacion de forma de un email, deliberadamente laxa: "algo@algo.algo" sin espacios.
# No se usa el validador Email de WTForms porque exige la dependencia `email_validator`, que
# seria una dependencia nueva del proyecto para algo que igual no puede decidir si una casilla
# existe. Lo unico que decide eso es mandarle un correo, y la epica excluye el correo.
PATRON_DE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MENSAJE_EMAIL_INVALIDO = "El email no tiene un formato válido."


def es_email_valido(email: str) -> bool:
    """Indica si el texto tiene forma de direccion de correo."""
    return bool(PATRON_DE_EMAIL.match((email or "").strip()))
