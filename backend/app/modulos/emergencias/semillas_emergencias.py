"""Datos semilla del módulo de emergencias (fixtures operativas)."""

from __future__ import annotations

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.modulos.emergencias.modelos import (
    Emergencia,
    EstadoEmergencia,
    NivelGravedad,
)
from app.modulos.organizaciones.modelos import Organizacion
from app.modulos.usuarios_roles.modelos import Usuario

# # # # # # # # # # # # Emergencias # # # # # # # # # # # #
EMERGENCIAS: list[dict] = [
    {
        "titulo": "Temporal severo con voladura de techos en Chascomús",
        "descripcion": (
            "Un temporal con ráfagas superiores a los 100 km/h"
            "provocó la voladura de techos en viviendas y galpones."
            "También se reportan la caída de árboles y postes de luz."
            "Se requiere asistencia para encontrar a 3 personas desaparecidas durante el temporal."
            "Solicitamos además apoyo médico para la atención y transporte de heridos."
        ),
        "nivel_gravedad": NivelGravedad.media,
        "zona_afectada": "Casco urbano y periurbano de Chascomús",
        "estado": EstadoEmergencia.registrada,
        "municipio_nombre": "Municipio de Chascomús",
        "usuario_email": "operador@chascomus.test",
    },
]


@registrar("emergencias")
def sembrar_emergencias() -> list[ResultadoSemilla]:

    resultado = ResultadoSemilla("emergencias")

    for datos in EMERGENCIAS:
        municipio = Organizacion.query.filter_by(nombre=datos["municipio_nombre"]).first()
        if municipio is None:
            raise ValueError(
                f"Municipio no encontrado: {datos['municipio_nombre']!r}. "
                f"Revisar si está declarado en organizaciones/semillas.py::ORGANIZACIONES"
            )

        usuario = Usuario.query.filter_by(email=datos["usuario_email"]).first()
        if usuario is None:
            raise ValueError(
                f"Usuario operador no encontrado: {datos['usuario_email']!r}. "
                f"Revisar si está declarado en usuarios_roles/semillas.py::USUARIOS?"
            )

        _, creada = obtener_o_crear(
            Emergencia,
            claves={"titulo": datos["titulo"]},
            valores={
                "descripcion": datos["descripcion"],
                "nivel_gravedad": datos["nivel_gravedad"],
                "zona_afectada": datos["zona_afectada"],
                "estado": datos["estado"],
                "municipio_id": municipio.id,
                "usuario_id": usuario.id,
            },
        )
        resultado.contar(creada)

    return [resultado]
