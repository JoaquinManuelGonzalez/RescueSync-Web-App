"""Datos semilla del módulo de emergencias (fixtures operativas)."""

from __future__ import annotations

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.modulos.emergencias.modelos import (
    Emergencia,
    EstadoEmergencia,
    NivelGravedad,
    TipoEmergencia,
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
        "tipo_emergencia": TipoEmergencia.otros,
        # "bonita_case_id": "111",
    },
    {
        "titulo": "Inundación en zona costera de Bahía Blanca",
        "descripcion": (
            "Lluvias intensas provocaron el desborde del arroyo Napostá. "
            "Se reportan viviendas evacuadas, cortes de rutas"
            "y pérdida de suministro eléctrico en amplios sectores."
            "Al menos 80 familias evacuadas que no pueden vovler a sus viviendas."
            "Se requiere asistencia inmediata para la población desplazada."
        ),
        "nivel_gravedad": NivelGravedad.critica,
        "zona_afectada": "Barrios alrededor del arroyo Napostá y costanera municipal",
        "estado": EstadoEmergencia.registrada,
        "municipio_nombre": "Municipalidad de Bahía Blanca",
        "usuario_email": "operador@bahia.test",
        "tipo_emergencia": TipoEmergencia.inundacion,
        # "bonita_case_id": "112",
    },
    {
        "titulo": "Incendio de forestal en Parque Pereyra",
        "descripcion": (
            "Un incendio se propagó desde los pastizales"
            "cercanos a la Autopista Dr. R. Balbín."
            "Viviendas rurales y producciones familiares afectadas."
            "Bomberos locales trabajan en el control del fuego"
            "pero necesitan refuerzos por la aparición de nuevos focos."
        ),
        "nivel_gravedad": NivelGravedad.baja,
        "zona_afectada": "A. Dr. R. Balbín y estación Pereyra, partido de La Plata",
        "estado": EstadoEmergencia.registrada,
        "municipio_nombre": "Municipalidad de La Plata",
        "usuario_email": "operador@laplata.test",
        "tipo_emergencia": TipoEmergencia.incendio,
        # "bonita_case_id": "113",
    },
    {
        "titulo": "PRUEBA - Selección municipal de ofertas en Pergamino",
        "descripcion": (
            "Caso de prueba para validar la selección por línea de oferta, "
            "el margen del 25% y la cobertura mínima del 75%."
        ),
        "nivel_gravedad": NivelGravedad.media,
        "zona_afectada": "Barrios periféricos de Pergamino",
        "estado": EstadoEmergencia.activa,
        "municipio_nombre": "Municipalidad de Pergamino",
        "usuario_email": "operador@pergamino.test",
        "tipo_emergencia": TipoEmergencia.otros,
        # Caso local de prueba: no tiene bonita_case_id ni integración con Bonita.
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
                "tipo_emergencia": datos["tipo_emergencia"],
                "zona_afectada": datos["zona_afectada"],
                "estado": datos["estado"],
                # "bonita_case_id": ...
                "municipio_id": municipio.id,
                "usuario_id": usuario.id,
            },
        )
        resultado.contar(creada)

    return [resultado]
