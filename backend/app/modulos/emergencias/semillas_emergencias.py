"""Datos semilla del módulo de emergencias (fixtures operativas)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.modulos.emergencias.modelos import (
    Emergencia,
    EstadoEmergencia,
    NivelGravedad,
    TipoEmergencia,
)
from app.modulos.organizaciones.modelos import Organizacion
from app.modulos.usuarios_roles.modelos import Usuario

TITULO_EMERGENCIA_COBERTURA_INSUFICIENTE = "PRUEBA - Cobertura parcial pendiente en Chascomús"

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
    {
        "titulo": TITULO_EMERGENCIA_COBERTURA_INSUFICIENTE,
        "descripcion": (
            "Caso de prueba para validar el panel de cobertura insuficiente y la "
            "aceptación de cobertura parcial desde el 75%."
        ),
        "nivel_gravedad": NivelGravedad.media,
        "zona_afectada": "Casco urbano de Chascomús",
        "estado": EstadoEmergencia.activa,
        "municipio_nombre": "Municipio de Chascomús",
        "usuario_email": "operador@chascomus.test",
        "tipo_emergencia": TipoEmergencia.otros,
    },
]

# Emergencias ya resueltas, con fecha de registro fija, para que el panel de auditoria tenga
# historia que mostrar: el filtro de octubre de 2026 y las tarjetas de finalizadas y canceladas.
# Las finalizadas y la activa tienen sus lotes, ofertas y adjudicacion en ofertas/semillas.py, y lo
# que hizo cada ONG despues en ejecucion_cierre/semillas.py.
EMERGENCIAS_HISTORICAS: list[dict] = [
    {
        "titulo": "Granizo sobre la zona hortícola de La Plata",
        "descripcion": (
            "Una tormenta de granizo dañó invernaderos y cultivos del cinturón hortícola. "
            "Familias productoras necesitaron nylon, herramientas y alimentos."
        ),
        "nivel_gravedad": NivelGravedad.media,
        "zona_afectada": "Cinturón hortícola de Abasto y Olmos, partido de La Plata",
        "estado": EstadoEmergencia.finalizada,
        "municipio_nombre": "Municipalidad de La Plata",
        "usuario_email": "operador@laplata.test",
        "tipo_emergencia": TipoEmergencia.otros,
        "creado_en": datetime(2026, 8, 18, 14, 30, tzinfo=UTC),
    },
    {
        "titulo": "Desborde de la laguna de Chascomús",
        "descripcion": (
            "La crecida de la laguna anegó la costanera y barrios bajos. "
            "Se evacuaron 40 familias y se requirieron colchones, agua y abrigo."
        ),
        "nivel_gravedad": NivelGravedad.alta,
        "zona_afectada": "Costanera y barrios ribereños de Chascomús",
        "estado": EstadoEmergencia.finalizada,
        "municipio_nombre": "Municipio de Chascomús",
        "usuario_email": "operador@chascomus.test",
        "tipo_emergencia": TipoEmergencia.inundacion,
        "creado_en": datetime(2026, 9, 7, 11, 0, tzinfo=UTC),
    },
    {
        "titulo": "Alerta por fuga de gas en el puerto de Bahía Blanca",
        "descripcion": (
            "Se reportó una posible fuga de gas en el área portuaria. "
            "La inspección descartó el riesgo y la alerta se dio de baja."
        ),
        "nivel_gravedad": NivelGravedad.alta,
        "zona_afectada": "Puerto de Ingeniero White, Bahía Blanca",
        "estado": EstadoEmergencia.cancelada,
        "municipio_nombre": "Municipalidad de Bahía Blanca",
        "usuario_email": "operador@bahia.test",
        "tipo_emergencia": TipoEmergencia.otros,
        "creado_en": datetime(2026, 9, 24, 18, 15, tzinfo=UTC),
    },
    {
        "titulo": "Incendio de pastizales en el periurbano de La Plata",
        "descripcion": (
            "El fuego avanzó sobre pastizales linderos a viviendas rurales. "
            "Se pidieron refuerzos de agua, insumos médicos y kits de higiene."
        ),
        "nivel_gravedad": NivelGravedad.media,
        "zona_afectada": "Lisandro Olmos y Etcheverry, partido de La Plata",
        "estado": EstadoEmergencia.finalizada,
        "municipio_nombre": "Municipalidad de La Plata",
        "usuario_email": "operador@laplata.test",
        "tipo_emergencia": TipoEmergencia.incendio,
        "creado_en": datetime(2026, 10, 4, 16, 45, tzinfo=UTC),
    },
    {
        "titulo": "Anegamiento de calles por lluvias en Chascomús",
        "descripcion": (
            "Lluvias persistentes anegaron calles de tierra y aislaron a vecinos de la zona rural. "
            "Se necesitaron alimentos no perecederos y agua potable."
        ),
        "nivel_gravedad": NivelGravedad.baja,
        "zona_afectada": "Zona rural de Chascomús",
        "estado": EstadoEmergencia.finalizada,
        "municipio_nombre": "Municipio de Chascomús",
        "usuario_email": "operador@chascomus.test",
        "tipo_emergencia": TipoEmergencia.inundacion,
        "creado_en": datetime(2026, 10, 11, 9, 20, tzinfo=UTC),
    },
    {
        "titulo": "Brote de gastroenteritis en barrios de Bahía Blanca",
        "descripcion": (
            "Se notificaron casos de gastroenteritis asociados al agua de red. "
            "Los análisis descartaron la contaminación y la emergencia se canceló."
        ),
        "nivel_gravedad": NivelGravedad.media,
        "zona_afectada": "Barrios Noroeste y Villa Rosas, Bahía Blanca",
        "estado": EstadoEmergencia.cancelada,
        "municipio_nombre": "Municipalidad de Bahía Blanca",
        "usuario_email": "operador@bahia.test",
        "tipo_emergencia": TipoEmergencia.epidemia,
        "creado_en": datetime(2026, 10, 19, 13, 10, tzinfo=UTC),
    },
    {
        "titulo": "Vientos fuertes con caída de árboles en Bahía Blanca",
        "descripcion": (
            "Ráfagas de más de 90 km/h derribaron árboles y tendido eléctrico. "
            "Hay viviendas con daños en techos y sectores sin suministro."
        ),
        "nivel_gravedad": NivelGravedad.alta,
        "zona_afectada": "Centro y barrio Universitario, Bahía Blanca",
        "estado": EstadoEmergencia.registrada,
        "municipio_nombre": "Municipalidad de Bahía Blanca",
        "usuario_email": "operador@bahia.test",
        "tipo_emergencia": TipoEmergencia.otros,
        "creado_en": datetime(2026, 10, 27, 20, 5, tzinfo=UTC),
    },
    {
        "titulo": "Temporal de viento y lluvia en Pergamino",
        "descripcion": (
            "Un temporal dejó calles anegadas, árboles caídos y barrios sin luz. "
            "Se necesitan rescatistas, generadores y alimentos para familias evacuadas."
        ),
        "nivel_gravedad": NivelGravedad.critica,
        "zona_afectada": "Barrios Acevedo y Centenario, Pergamino",
        # Adjudicada y en ejecucion: ofertas/semillas.py y ejecucion_cierre/semillas.py.
        "estado": EstadoEmergencia.activa,
        "municipio_nombre": "Municipalidad de Pergamino",
        "usuario_email": "operador@pergamino.test",
        "tipo_emergencia": TipoEmergencia.otros,
        "creado_en": datetime(2026, 11, 3, 8, 0, tzinfo=UTC),
    },
]


@registrar("emergencias")
def sembrar_emergencias() -> list[ResultadoSemilla]:

    resultado = ResultadoSemilla("emergencias")

    for datos in [*EMERGENCIAS, *EMERGENCIAS_HISTORICAS]:
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

        valores = {
            "descripcion": datos["descripcion"],
            "nivel_gravedad": datos["nivel_gravedad"],
            "tipo_emergencia": datos["tipo_emergencia"],
            "zona_afectada": datos["zona_afectada"],
            "estado": datos["estado"],
            # "bonita_case_id": ...
            "municipio_id": municipio.id,
            "usuario_id": usuario.id,
        }
        # Sin fecha propia la emergencia queda registrada "ahora", por el server_default.
        if "creado_en" in datos:
            valores["creado_en"] = datos["creado_en"]

        _, creada = obtener_o_crear(
            Emergencia,
            claves={"titulo": datos["titulo"]},
            valores=valores,
        )
        resultado.contar(creada)

    return [resultado]
