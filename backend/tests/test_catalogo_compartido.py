"""Contrato del catálogo de recursos compartido con la API del Sistema Nacional.

Bonita reenvía a `POST /ofertas/evaluacion` del Sistema Nacional los `codigo_recurso` que arma
`GET /ofertas/consolidadas/<convocatoria_id>`, sin traducirlos. Si la web tiene un ítem que la API
no, la evaluación entera falla con 404; si el tipo o el consumible difieren, la API exige otra
certificación o compromete stock que la web no espera.

`CATALOGO_COMPARTIDO` es una copia literal de la misma constante en
`tests/test_catalogo_compartido.py` del repo RescueSync-API-Sistema-Nacional, que la compara con
las semillas de la API (`app/modulos/organizaciones/semillas.py`). Si cambia el catálogo de la
web, se actualizan las dos copias y las semillas de la API.
"""

from __future__ import annotations

from app.modulos.emergencias.semillas_items import ITEMS, _codigo_recurso

# codigo_recurso -> (categoria, unidad de medida, consumible), en el orden de ITEMS.
CATALOGO_COMPARTIDO: dict[str, tuple[str, str, bool]] = {
    "RSR-PARAMEDICOS": ("personal_medico", "personas", False),
    "RSR-MEDICOS_DE_URGENCIA": ("personal_medico", "personas", False),
    "RSR-ENFERMEROS": ("personal_medico", "personas", False),
    "RSR-RESCATISTAS": ("rescate", "personas", False),
    "RSR-PERROS_DE_BUSQUEDA": ("rescate", "unidades", False),
    "RSR-BOMBEROS": ("rescate", "personas", False),
    "RSR-BRIGADISTAS": ("rescate", "personas", False),
    "RSR-RACIONES_DE_ALIMENTO_NO_PERECEDERO": ("alimentos", "raciones", True),
    "RSR-LATAS_DE_ARVEJAS": ("alimentos", "kg", True),
    "RSR-POLENTA": ("alimentos", "kg", True),
    "RSR-FIDEOS": ("alimentos", "kg", True),
    "RSR-ARROZ": ("alimentos", "kg", True),
    "RSR-ACEITE": ("alimentos", "raciones", True),
    "RSR-GALLETITAS_DE_AGUA": ("alimentos", "unidades", True),
    "RSR-GALLETITAS_DULCES": ("alimentos", "unidades", True),
    "RSR-HARINA_DE_TRIGO": ("alimentos", "kg", True),
    "RSR-AZUCAR": ("alimentos", "kg", True),
    "RSR-LENTEJAS": ("alimentos", "kg", True),
    "RSR-CAFE": ("alimentos", "kg", True),
    "RSR-YERBA": ("alimentos", "kg", True),
    "RSR-LECHE_EN_POLVO": ("alimentos", "kg", True),
    "RSR-AGUA_POTABLE_ENVASADA": ("agua", "litros", True),
    "RSR-TANQUES_DE_AGUA": ("agua", "unidades", True),
    "RSR-FRAZADAS": ("abrigo", "unidades", True),
    "RSR-COLCHONES": ("abrigo", "unidades", True),
    "RSR-CARPAS_FAMILIARES": ("abrigo", "unidades", True),
    "RSR-ROPA_DE_INVIERNO": ("abrigo", "unidades", True),
    "RSR-ROPA_DE_VERANO": ("abrigo", "unidades", True),
    "RSR-BOTIQUINES_DE_PRIMEROS_AUXILIOS": ("medicamentos", "unidades", True),
    "RSR-ANALGESICOS": ("medicamentos", "unidades", True),
    "RSR-PARACETAMOL": ("medicamentos", "unidades", True),
    "RSR-IBUPROFENO": ("medicamentos", "unidades", True),
    "RSR-ANTIBIOTICOS": ("medicamentos", "unidades", True),
    "RSR-PANALES_PARA_ADULTO": ("medicamentos", "unidades", True),
    "RSR-SUPLEMENTO_ALIMENTICIO": ("medicamentos", "unidades", True),
    "RSR-SUERO_FISIOLOGICO": ("medicamentos", "unidades", True),
    "RSR-RETROEXCAVADORAS": ("maquinaria", "unidades", False),
    "RSR-CAMIONES_DE_CARGA": ("maquinaria", "unidades", False),
    "RSR-GENERADORES_ELECTRICOS": ("maquinaria", "unidades", False),
    "RSR-AMBULANCIAS": ("maquinaria", "unidades", False),
    "RSR-VOLUNTARIOS_GENERALES": ("otro", "personas", False),
    "RSR-TOALLITAS_FEMENINAS": ("otro", "unidades", True),
    "RSR-JABON": ("otro", "unidades", True),
    "RSR-TOALLAS_JABONOSAS": ("otro", "unidades", True),
    "RSR-KIT_HIGIENE_BUCAL": ("otro", "unidades", True),
    "RSR-PANALES_PARA_BEBES": ("otro", "unidades", True),
}


def test_catalogo_de_la_web_es_igual_al_del_sistema_nacional():
    catalogo = {
        _codigo_recurso(nombre): (categoria.value, unidad, consumible)
        for nombre, categoria, unidad, _descripcion, consumible in ITEMS
    }

    faltan = sorted(CATALOGO_COMPARTIDO.keys() - catalogo.keys())
    sobran = sorted(catalogo.keys() - CATALOGO_COMPARTIDO.keys())
    distintos = {
        codigo: {"web": catalogo[codigo], "contrato": esperado}
        for codigo, esperado in CATALOGO_COMPARTIDO.items()
        if codigo in catalogo and catalogo[codigo] != esperado
    }
    assert not (faltan or sobran or distintos), (
        "El catálogo de semillas_items.py ya no coincide con el del Sistema Nacional. Si "
        "agregaste o cambiaste un ítem, replicalo en RescueSync-API-Sistema-Nacional "
        "(app/modulos/organizaciones/semillas.py) y en las dos copias de CATALOGO_COMPARTIDO; "
        "si no, Bonita recibe 404 al enviar las ofertas. "
        f"Nuevos en la web: {sobran}. Quitados de la web: {faltan}. Distintos: {distintos}."
    )
