"""Primitivas de seguridad compartidas.

El hasheo de contrasenas se centraliza aca para que nadie tenga que elegir un algoritmo al
escribir un modelo, un formulario o un seeder
"""

from __future__ import annotations

from werkzeug.security import check_password_hash, generate_password_hash

# scrypt es el algoritmo por defecto de Werkzeug 3 y no necesita dependencias extra.
METODO_HASH = "scrypt"


def hashear_contrasena(contrasena: str) -> str:
    """Devuelve el hash a guardar en la base. La contrasena en claro nunca se persiste."""
    return generate_password_hash(contrasena, method=METODO_HASH)


def verificar_contrasena(hash_almacenado: str, contrasena: str) -> bool:
    """Compara una contrasena en claro contra el hash guardado, en tiempo constante."""
    return check_password_hash(hash_almacenado, contrasena)
