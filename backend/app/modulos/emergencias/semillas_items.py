"""Datos semilla para el módulo de emergencias.
Notas:
    * se identifica cada Item por su nombre
    * No se siembran Emergencias, Lotes ni Convocatorias ya que son datos que se generan por el flujo de la aplicación.
"""

from __future__ import annotations

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.modulos.emergencias.modelos import Item, TipoNecesidad

# # # # # # # # # # # # Items # # # # # # # # # # # #
ITEMS: list[tuple[str, TipoNecesidad, str, str | None]] = [
    # --- Personal médico -----------------------------------------------------------
    (
        "Paramédicos",
        TipoNecesidad.personal_medico,
        "personas",
        "Personal de atención prehospitalaria con certificación vigente.",
    ),
    (
        "Médicos de urgencia",
        TipoNecesidad.personal_medico,
        "personas",
        "Médicos con especialidad en emergencias.",
    ),
    (
        "Enfermeros",
        TipoNecesidad.personal_medico,
        "personas",
        "Personal de enfermería para primeros auxilios y cuidados básicos.",
    ),

    # --- Rescate -----------------------------------------------------------
    (
        "Rescatistas",
        TipoNecesidad.rescate,
        "personas",
        "Personal entrenado en búsqueda y rescate urbano.",
    ),
    (
        "Perros de búsqueda",
        TipoNecesidad.rescate,
        "unidades",
        "Caninos entrenados para detección de personas.",
    ),

    # --- Bomberos -----------------------------------------------------------
    (
        "Bomberos",
        TipoNecesidad.rescate,
        "personas",
        "Personal civil de bomberos voluntarios.",
    ),
    (
        "Brigadistas",
        TipoNecesidad.rescate,
        "personas",
        "Bomberos civiles voluntarios especializados los incendios forestales.",
    ),

    # --- Alimentos ---------------------------------------------------------
    (
        "Raciones de alimento no perecedero",
        TipoNecesidad.alimentos,
        "raciones",
        "Raciones individuales instantáneas, listas para consumo.",
    ),
    (
        "Latas de arvejas",
        TipoNecesidad.alimentos,
        "kg",
        None,
    ),
    (
        "Polenta",
        TipoNecesidad.alimentos,
        "kg",
        None,
    ),
    (
        "Fideos",
        TipoNecesidad.alimentos,
        "kg",
        None,
    ),
    (
        "Arroz",
        TipoNecesidad.alimentos,
        "kg",
        None,
    ),
    (
        "Aceite",
        TipoNecesidad.alimentos,
        "raciones",
        None,
    ),
    (
        "Galletitas de agua",
        TipoNecesidad.alimentos,
        "unidades",
        None,
    ),
    (
        "Galletitas dulces",
        TipoNecesidad.alimentos,
        "unidades",
        None,
    ),
    (
        "Harina de trigo",
        TipoNecesidad.alimentos,
        "kg",
        None,
    ),
    (
        "Azúcar",
        TipoNecesidad.alimentos,
        "kg",
        None,
    ),
    (
        "Lentejas",
        TipoNecesidad.alimentos,
        "kg",
        None,
    ),
    (
        "Café",
        TipoNecesidad.alimentos,
        "kg",
        None,
    ),
    (
        "Yerba",
        TipoNecesidad.alimentos,
        "kg",
        None,
    ),
    (
        "Leche en polvo",
        TipoNecesidad.alimentos,
        "kg",
        None,
    ),

    # --- Agua --------------------------------------------------------------
    (
        "Agua potable envasada",
        TipoNecesidad.agua,
        "litros",
        "Botellas selladas aptas para consumo humano.",
    ),
    (
        "Tanques de agua",
        TipoNecesidad.agua,
        "unidades",
        "Tanques de 1000 L para distribución comunitaria.",
    ),

    # --- Abrigo ------------------------------------------------------------
    (
        "Frazadas",
        TipoNecesidad.abrigo,
        "unidades",
        None,
    ),
    (
        "Colchones",
        TipoNecesidad.abrigo,
        "unidades",
        "Colchones de goma espuma para refugios temporales.",
    ),
    (
        "Carpas familiares",
        TipoNecesidad.abrigo,
        "unidades",
        "Carpas para 4-6 personas.",
    ),
    (
        "Ropa de invierno",
        TipoNecesidad.abrigo,
        "unidades",
        "Donaciones de ropa apta para temperaturas por debajo de los 15°.",
    ),
    (
        "Ropa de verano",
        TipoNecesidad.abrigo,
        "unidades",
        "Donaciones de ropa apta para temperaturas por encima de los 15°.",
    ),

    # --- Medicamentos ------------------------------------------------------
    (
        "Botiquines de primeros auxilios",
        TipoNecesidad.medicamentos,
        "unidades",
        "Kit básico de primeros auxilios.",
    ),
    (
        "Analgésicos",
        TipoNecesidad.medicamentos,
        "unidades",
        "Comprimidos de uso general.",
    ),
    (
        "Paracetamol",
        TipoNecesidad.medicamentos,
        "unidades",
        "Genérico. Comprimidos de 200, 600, 800 o 1000 mgr.",
    ),
    (
        "Ibuprofeno",
        TipoNecesidad.medicamentos,
        "unidades",
        "Genérico. Comprimidos de 200, 600 o 800 mgr.",
    ),
    (
        "Antibióticos",
        TipoNecesidad.medicamentos,
        "unidades",
        "Comprimidos de uso general.",
    ),
    (
        "Pañales para adulto",
        TipoNecesidad.medicamentos,
        "unidades",
        None,
    ),
    (
        "Suplemento alimenticio",
        TipoNecesidad.medicamentos,
        "unidades",
        "Fuente adicional de nutrientes para personas en situaciones críticas.",
    ),
    (
        "Suero fisiológico",
        TipoNecesidad.medicamentos,
        "unidades",
        "Para reponer líquidos, limpiar ojos, lavar heridas y quemaduras, y diluir medicamentos.",
    ),

    # --- Maquinaria --------------------------------------------------------
    (
        "Retroexcavadoras",
        TipoNecesidad.maquinaria,
        "unidades",
        "Para remoción de escombros.",
    ),
    (
        "Camiones de carga",
        TipoNecesidad.maquinaria,
        "unidades",
        "Capacidad mínima 5 toneladas.",
    ),
    (
        "Generadores eléctricos",
        TipoNecesidad.maquinaria,
        "unidades",
        "Generadores portátiles 5 kVA.",
    ),
    (
        "Ambulancias",
        TipoNecesidad.maquinaria,
        "unidades",
        "Unidades de traslado medicalizado.",
    ),

    # --- Otro --------------------------------------------------------------
    (
        "Voluntarios generales",
        TipoNecesidad.otro,
        "personas",
        "Personal de apoyo voluntario no especializado.",
    ),
    (
        "Toallitas femeninas",
        TipoNecesidad.otro,
        "unidades",
        "Para higiene menstrual.",
    ),
    (
        "Jabón",
        TipoNecesidad.otro,
        "unidades",
        "Barras de jabón para aseo personal.",
    ),
    (
        "Toallas jabonosas",
        TipoNecesidad.otro,
        "unidades",
        "Toallas jabonosas desechables y sin enjuague. De aseo para adultos, bebés y niños.",
    ),
    (
        "Kit higiene bucal",
        TipoNecesidad.otro,
        "unidades",
        "Kit individual de cepillo de dientes y pasta dental.",
    ),
    (
        "Pañales para bebes",
        TipoNecesidad.otro,
        "unidades",
        "Pañales descartables.",
    ),
]


@registrar("items")
def sembrar_items() -> list[ResultadoSemilla]:

    resultado = ResultadoSemilla("items")

    for nombre, categoria, unidad_medida, descripcion in ITEMS:
        _, creado = obtener_o_crear(
            Item,
            claves={"nombre": nombre},
            valores={
                "categoria": categoria,
                "unidad_medida": unidad_medida,
                "descripcion": descripcion,
            },
        )
        resultado.contar(creado)

    return [resultado]
