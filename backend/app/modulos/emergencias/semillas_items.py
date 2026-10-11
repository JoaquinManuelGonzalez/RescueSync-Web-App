"""Datos semilla para el módulo de emergencias.
Notas:
    * Se identifica cada Item por su nombre
    * No se siembran Lotes ni Convocatorias. Son datos que se generan por el flujo de la aplicación.
"""

from __future__ import annotations

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.modulos.emergencias.modelos import Item, TipoNecesidad

# # # # # # # # # # # # Items # # # # # # # # # # # #
ITEMS: list[tuple[str, TipoNecesidad, str, str | None, bool]] = [
    # --- Personal médico -----------------------------------------------------------
    (
        "Paramédicos",
        TipoNecesidad.personal_medico,
        "personas",
        "Personal de atención prehospitalaria con certificación vigente.",
        False,
    ),
    (
        "Médicos de urgencia",
        TipoNecesidad.personal_medico,
        "personas",
        "Médicos con especialidad en emergencias.",
        False,
    ),
    (
        "Enfermeros",
        TipoNecesidad.personal_medico,
        "personas",
        "Personal de enfermería para primeros auxilios y cuidados básicos.",
        False,
    ),
    # --- Rescate -----------------------------------------------------------
    (
        "Rescatistas",
        TipoNecesidad.rescate,
        "personas",
        "Personal entrenado en búsqueda y rescate urbano.",
        False,
    ),
    (
        "Perros de búsqueda",
        TipoNecesidad.rescate,
        "unidades",
        "Caninos entrenados para detección de personas.",
        False,
    ),
    # --- Bomberos -----------------------------------------------------------
    (
        "Bomberos",
        TipoNecesidad.rescate,
        "personas",
        "Personal civil de bomberos voluntarios.",
        False,
    ),
    (
        "Brigadistas",
        TipoNecesidad.rescate,
        "personas",
        "Bomberos civiles voluntarios especializados los incendios forestales.",
        False,
    ),
    # --- Alimentos ---------------------------------------------------------
    (
        "Raciones de alimento no perecedero",
        TipoNecesidad.alimentos,
        "raciones",
        "Raciones individuales instantáneas, listas para consumo.",
        True,
    ),
    (
        "Latas de arvejas",
        TipoNecesidad.alimentos,
        "kg",
        None,
        True,
    ),
    (
        "Polenta",
        TipoNecesidad.alimentos,
        "kg",
        None,
        True,
    ),
    (
        "Fideos",
        TipoNecesidad.alimentos,
        "kg",
        None,
        True,
    ),
    (
        "Arroz",
        TipoNecesidad.alimentos,
        "kg",
        None,
        True,
    ),
    (
        "Aceite",
        TipoNecesidad.alimentos,
        "raciones",
        None,
        True,
    ),
    (
        "Galletitas de agua",
        TipoNecesidad.alimentos,
        "unidades",
        None,
        True,
    ),
    (
        "Galletitas dulces",
        TipoNecesidad.alimentos,
        "unidades",
        None,
        True,
    ),
    (
        "Harina de trigo",
        TipoNecesidad.alimentos,
        "kg",
        None,
        True,
    ),
    (
        "Azúcar",
        TipoNecesidad.alimentos,
        "kg",
        None,
        True,
    ),
    (
        "Lentejas",
        TipoNecesidad.alimentos,
        "kg",
        None,
        True,
    ),
    (
        "Café",
        TipoNecesidad.alimentos,
        "kg",
        None,
        True,
    ),
    (
        "Yerba",
        TipoNecesidad.alimentos,
        "kg",
        None,
        True,
    ),
    (
        "Leche en polvo",
        TipoNecesidad.alimentos,
        "kg",
        None,
        True,
    ),
    # --- Agua --------------------------------------------------------------
    (
        "Agua potable envasada",
        TipoNecesidad.agua,
        "litros",
        "Botellas selladas aptas para consumo humano.",
        True,
    ),
    (
        "Tanques de agua",
        TipoNecesidad.agua,
        "unidades",
        "Tanques de 1000 L para distribución comunitaria.",
        True,
    ),
    # --- Abrigo ------------------------------------------------------------
    (
        "Frazadas",
        TipoNecesidad.abrigo,
        "unidades",
        None,
        True,
    ),
    (
        "Colchones",
        TipoNecesidad.abrigo,
        "unidades",
        "Colchones de goma espuma para refugios temporales.",
        True,
    ),
    (
        "Carpas familiares",
        TipoNecesidad.abrigo,
        "unidades",
        "Carpas para 4-6 personas.",
        True,
    ),
    (
        "Ropa de invierno",
        TipoNecesidad.abrigo,
        "unidades",
        "Donaciones de ropa apta para temperaturas por debajo de los 15°.",
        True,
    ),
    (
        "Ropa de verano",
        TipoNecesidad.abrigo,
        "unidades",
        "Donaciones de ropa apta para temperaturas por encima de los 15°.",
        True,
    ),
    # --- Medicamentos ------------------------------------------------------
    (
        "Botiquines de primeros auxilios",
        TipoNecesidad.medicamentos,
        "unidades",
        "Kit básico de primeros auxilios.",
        True,
    ),
    (
        "Analgésicos",
        TipoNecesidad.medicamentos,
        "unidades",
        "Comprimidos de uso general.",
        True,
    ),
    (
        "Paracetamol",
        TipoNecesidad.medicamentos,
        "unidades",
        "Genérico. Comprimidos de 200, 600, 800 o 1000 mgr.",
        True,
    ),
    (
        "Ibuprofeno",
        TipoNecesidad.medicamentos,
        "unidades",
        "Genérico. Comprimidos de 200, 600 o 800 mgr.",
        True,
    ),
    (
        "Antibióticos",
        TipoNecesidad.medicamentos,
        "unidades",
        "Comprimidos de uso general.",
        True,
    ),
    (
        "Pañales para adulto",
        TipoNecesidad.medicamentos,
        "unidades",
        None,
        True,
    ),
    (
        "Suplemento alimenticio",
        TipoNecesidad.medicamentos,
        "unidades",
        "Fuente adicional de nutrientes para personas en situaciones críticas.",
        True,
    ),
    (
        "Suero fisiológico",
        TipoNecesidad.medicamentos,
        "unidades",
        "Para reponer líquidos, limpiar ojos, lavar heridas y quemaduras, y diluir medicamentos.",
        True,
    ),
    # --- Maquinaria --------------------------------------------------------
    (
        "Retroexcavadoras",
        TipoNecesidad.maquinaria,
        "unidades",
        "Para remoción de escombros.",
        False,
    ),
    (
        "Camiones de carga",
        TipoNecesidad.maquinaria,
        "unidades",
        "Capacidad mínima 5 toneladas.",
        False,
    ),
    (
        "Generadores eléctricos",
        TipoNecesidad.maquinaria,
        "unidades",
        "Generadores portátiles 5 kVA.",
        False,
    ),
    (
        "Ambulancias",
        TipoNecesidad.maquinaria,
        "unidades",
        "Unidades de traslado medicalizado.",
        False,
    ),
    # --- Otro --------------------------------------------------------------
    (
        "Voluntarios generales",
        TipoNecesidad.otro,
        "personas",
        "Personal de apoyo voluntario no especializado.",
        False,
    ),
    (
        "Toallitas femeninas",
        TipoNecesidad.otro,
        "unidades",
        "Para higiene menstrual.",
        True,
    ),
    (
        "Jabón",
        TipoNecesidad.otro,
        "unidades",
        "Barras de jabón para aseo personal.",
        True,
    ),
    (
        "Toallas jabonosas",
        TipoNecesidad.otro,
        "unidades",
        "Toallas jabonosas desechables y sin enjuague. De aseo para adultos, bebés y niños.",
        True,
    ),
    (
        "Kit higiene bucal",
        TipoNecesidad.otro,
        "unidades",
        "Kit individual de cepillo de dientes y pasta dental.",
        True,
    ),
    (
        "Pañales para bebes",
        TipoNecesidad.otro,
        "unidades",
        "Pañales descartables.",
        True,
    ),
]


@registrar("items")
def sembrar_items() -> list[ResultadoSemilla]:

    resultado = ResultadoSemilla("items")

    for nombre, categoria, unidad_medida, descripcion, consumible in ITEMS:
        _, creado = obtener_o_crear(
            Item,
            claves={"nombre": nombre},
            valores={
                "categoria": categoria,
                "unidad_medida": unidad_medida,
                "descripcion": descripcion,
                "consumible": consumible,
            },
        )
        resultado.contar(creado)

    return [resultado]
