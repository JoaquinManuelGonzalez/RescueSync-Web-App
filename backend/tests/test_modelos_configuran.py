"""Verificacion de que el mapeo de SQLAlchemy es consistente.

Los `relationship()` mal apareados no fallan al importar el modulo: SQLAlchemy configura los
mappers de forma perezosa, en la primera consulta real. Sin este test, un `back_populates` que
apunta a una propiedad inexistente pasa la revision y la suite entera, y revienta recien cuando
alguien intenta autenticarse o correr `flask seed`.
"""

from __future__ import annotations

from sqlalchemy.orm import configure_mappers

from app.modulos import importar_modelos


def test_configurar_mappers_no_falla(app) -> None:
    """Fuerza la configuracion de todos los mappers declarados por los modulos de dominio."""
    with app.app_context():
        importar_modelos()
        configure_mappers()
