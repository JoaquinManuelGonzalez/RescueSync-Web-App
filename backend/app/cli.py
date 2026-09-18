"""Comandos de linea de la aplicacion (`flask <comando>`)."""

from __future__ import annotations

import sys

import click
from flask import Flask
from sqlalchemy import inspect, text

from app.core.semillas import SEEDERS, ResultadoSemilla, importar_seeders
from app.extensiones import db

# Texto exacto exigido por el criterio de aceptacion CA-03 de la HU de datos semilla.
MENSAJE_SIN_MIGRAR = "Ejecute las migraciones antes de cargar los datos semilla"


def _base_migrada() -> bool:
    """Indica si el esquema fue aplicado, mirando la tabla de control de Alembic."""
    inspector = inspect(db.engine)
    if not inspector.has_table("alembic_version"):
        return False
    revision = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return revision is not None


def _imprimir_resumen(resultados: list[ResultadoSemilla]) -> None:
    total_creados = sum(resultado.creados for resultado in resultados)
    total_existentes = sum(resultado.existentes for resultado in resultados)

    click.echo("")
    click.echo(f"{'Entidad':<28}{'Creados':>10}{'Ya existian':>14}")
    click.echo("-" * 52)
    for resultado in sorted(resultados, key=lambda item: item.entidad):
        click.echo(f"{resultado.entidad:<28}{resultado.creados:>10}{resultado.existentes:>14}")
    click.echo("-" * 52)
    click.echo(f"{'TOTAL':<28}{total_creados:>10}{total_existentes:>14}")

    emails = [email for resultado in resultados for email in resultado.emails]
    if emails:
        click.echo("")
        click.echo("Usuarios disponibles:")
        for email in sorted(emails):
            click.echo(f"  - {email}")


def registrar_comandos(app: Flask) -> None:
    """Engancha los comandos de la aplicacion a la CLI de Flask."""

    @app.cli.command("seed")
    def seed() -> None:
        """Carga los datos semilla del proyecto. Se puede ejecutar las veces que haga falta."""
        if not _base_migrada():
            click.echo(MENSAJE_SIN_MIGRAR, err=True)
            sys.exit(1)

        importar_seeders()

        if not SEEDERS:
            click.echo("No hay seeders registrados todavia.")
            click.echo(
                "El esquema de dominio esta en definicion: cuando existan los modelos, cada "
                "modulo registra el suyo. Ver el docstring de app/core/semillas.py."
            )
            return

        resultados: list[ResultadoSemilla] = []
        try:
            for seeder in SEEDERS:
                resultados.extend(seeder.funcion())
            # Una sola transaccion para todos los seeders: si uno falla, no queda media carga.
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        _imprimir_resumen(resultados)
