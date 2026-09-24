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

    @app.cli.command("crear-administrador")
    @click.option("--email", required=True, help="Email con el que va a iniciar sesion.")
    @click.option("--nombre", required=True, help="Nombre completo de la persona.")
    @click.option(
        "--contrasena",
        default=None,
        help="Contrasena inicial. Si se omite, se genera una y se imprime una sola vez.",
    )
    def crear_administrador(email: str, nombre: str, contrasena: str | None) -> None:
        """Crea la primera cuenta de administrador.

        Es el arranque en frio del sistema: el panel de gestion de usuarios exige estar
        autenticado como administrador, asi que la primera de esas cuentas no puede salir de
        ahi. Despues de esta, todas las demas se dan de alta desde el panel.
        """
        from app.core.acceso.permisos import NombreRol
        from app.core.acceso.seguridad import generar_contrasena
        from app.modulos.usuarios_roles import servicios

        if not _base_migrada():
            click.echo(MENSAJE_SIN_MIGRAR, err=True)
            sys.exit(1)

        generada = contrasena is None
        if generada:
            contrasena = generar_contrasena()

        try:
            usuario = servicios.crear_usuario(
                email=email,
                nombre_completo=nombre,
                contrasena=contrasena,
                nombre_rol=NombreRol.ADMINISTRADOR,
                # El administrador de arranque no tiene a quien pedirle un cambio de clave.
                debe_cambiar_contrasena=False,
            )
        except Exception as error:
            db.session.rollback()
            click.echo(f"No se pudo crear la cuenta: {error}", err=True)
            sys.exit(1)

        click.echo(f"Administrador creado: {usuario.email}")
        if generada:
            click.echo("")
            click.echo(f"Contrasena generada: {contrasena}")
            click.echo("Guardala ahora: no se vuelve a mostrar.")
