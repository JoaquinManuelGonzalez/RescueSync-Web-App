"""Primitivas de seguridad compartidas.

El hasheo de contrasenas se centraliza aca para que nadie tenga que elegir un algoritmo al
escribir un modelo, un formulario o un seeder
"""

from __future__ import annotations

import re
import secrets
import string

from werkzeug.security import check_password_hash, generate_password_hash

# scrypt es el algoritmo por defecto de Werkzeug 3 y no necesita dependencias extra.
METODO_HASH = "scrypt"


def hashear_contrasena(contrasena: str) -> str:
    """Devuelve el hash a guardar en la base. La contrasena en claro nunca se persiste."""
    return generate_password_hash(contrasena, method=METODO_HASH)


def verificar_contrasena(hash_almacenado: str, contrasena: str) -> bool:
    """Compara una contrasena en claro contra el hash guardado, en tiempo constante."""
    return check_password_hash(hash_almacenado, contrasena)


# --- Politica de contrasena ---------------------------------------------------
#
# Una contrasena nueva (alta, restablecimiento o cambio propio) tiene que tener al menos
# `CONTRASENA_LONGITUD_MINIMA` caracteres, una mayuscula, un numero y un caracter especial.
# Es la unica definicion de la regla: la usan los formularios, los servicios y la CLI, y la
# interfaz muestra los mismos textos. La longitud la fija la configuracion; los tipos de
# caracter son fijos. No se aplica al ingreso: una clave vieja tiene que poder entrar a
# cambiarse.

REQUISITO_LONGITUD = "longitud"
REQUISITO_MAYUSCULA = "mayuscula"
REQUISITO_NUMERO = "numero"
REQUISITO_ESPECIAL = "especial"


def _es_especial(caracter: str) -> bool:
    """Todo lo que no es letra, numero ni espacio: . - _ ! ? @ # $ % & * ..."""
    return not caracter.isalnum() and not caracter.isspace()


def requisitos_de_contrasena(longitud_minima: int) -> dict[str, str]:
    """Cada requisito con su texto, en el orden en que se muestran."""
    return {
        REQUISITO_LONGITUD: f"al menos {longitud_minima} caracteres",
        REQUISITO_MAYUSCULA: "una letra mayúscula",
        REQUISITO_NUMERO: "un número",
        REQUISITO_ESPECIAL: "un carácter especial (por ejemplo . - _ ! ? @ #)",
    }


def requisitos_incumplidos(contrasena: str, longitud_minima: int) -> list[str]:
    """Los requisitos que la contrasena no cumple. Vacia si cumple todos."""
    contrasena = contrasena or ""
    cumplidos = {
        REQUISITO_LONGITUD: len(contrasena) >= longitud_minima,
        REQUISITO_MAYUSCULA: any(caracter.isupper() for caracter in contrasena),
        REQUISITO_NUMERO: any(caracter.isdigit() for caracter in contrasena),
        REQUISITO_ESPECIAL: any(_es_especial(caracter) for caracter in contrasena),
    }
    return [requisito for requisito, cumple in cumplidos.items() if not cumple]


def _enumerar(partes: list[str]) -> str:
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " y " + partes[-1]


def mensaje_de_politica(incumplidos: list[str], longitud_minima: int) -> str:
    """Mensaje de error para mostrar junto al campo: dice exactamente que falta."""
    textos = requisitos_de_contrasena(longitud_minima)
    return f"La contraseña tiene que tener {_enumerar([textos[uno] for uno in incumplidos])}."


def describir_politica(longitud_minima: int) -> str:
    """La regla completa, para el texto de ayuda de los formularios."""
    textos = list(requisitos_de_contrasena(longitud_minima).values())
    return f"Tiene que tener {_enumerar(textos)}."


def generar_contrasena(longitud: int = 16) -> str:
    """Contrasena aleatoria que cumple la politica, para la CLI de arranque."""
    especiales = "-_.!?@#"
    alfabeto = string.ascii_letters + string.digits + especiales
    while True:
        candidata = "".join(secrets.choice(alfabeto) for _ in range(longitud))
        if not requisitos_incumplidos(candidata, longitud):
            return candidata


# Verificacion de forma de un email, deliberadamente laxa: "algo@algo.algo" sin espacios.
# No se usa el validador Email de WTForms porque exige la dependencia `email_validator`, que
# seria una dependencia nueva del proyecto para algo que igual no puede decidir si una casilla
# existe. Lo unico que decide eso es mandarle un correo, y la epica excluye el correo.
PATRON_DE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MENSAJE_EMAIL_INVALIDO = "El email no tiene un formato válido."


def es_email_valido(email: str) -> bool:
    """Indica si el texto tiene forma de direccion de correo."""
    return bool(PATRON_DE_EMAIL.match((email or "").strip()))
