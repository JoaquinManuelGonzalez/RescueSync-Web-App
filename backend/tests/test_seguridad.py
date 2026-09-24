"""Primitivas de seguridad: hasheo con sal y forma del email."""

from __future__ import annotations

from app.core.acceso.seguridad import (
    es_email_valido,
    hashear_contrasena,
    verificar_contrasena,
)


def test_dos_hashes_de_la_misma_contrasena_son_distintos() -> None:
    """La sal se genera por hash: dos hashes iguales delatarian que no hay sal."""
    primero = hashear_contrasena("Clave-Larga-2026")
    segundo = hashear_contrasena("Clave-Larga-2026")

    assert primero != segundo
    assert primero.startswith("scrypt:")


def test_la_contrasena_en_claro_no_aparece_en_el_hash() -> None:
    assert "Clave-Larga-2026" not in hashear_contrasena("Clave-Larga-2026")


def test_verificar_contrasena_correcta_devuelve_verdadero() -> None:
    assert verificar_contrasena(hashear_contrasena("Clave-Larga-2026"), "Clave-Larga-2026")


def test_verificar_contrasena_incorrecta_devuelve_falso() -> None:
    assert not verificar_contrasena(hashear_contrasena("Clave-Larga-2026"), "otra-cosa")


def test_email_con_forma_valida_se_acepta() -> None:
    assert es_email_valido("operador@chascomus.test")
    assert es_email_valido("  operador@chascomus.test  ")


def test_email_sin_forma_valida_se_rechaza() -> None:
    for invalido in ("sin-arroba", "sin@dominio", "con espacio@x.test", "@x.test", ""):
        assert not es_email_valido(invalido), invalido
