"""Reglas de negocio de organizaciones: cobertura, unicidad, tipo, inventario y verificacion."""

from __future__ import annotations

import pytest

from app.core.errores import ConflictoDeEstado, RecursoNoEncontrado, SolicitudInvalida
from app.modulos.organizaciones import servicios


def _organizacion(nombre: str):
    return next(una for una in servicios.listar() if una.nombre == nombre)


# --- Zona de cobertura ----------------------------------------------------------


def test_las_zonas_se_normalizan_sin_repetidos_y_ordenadas(app) -> None:
    with app.app_context():
        zonas = servicios.normalizar_zonas(
            [
                {"provincia": "Salta", "localidad": "  Cafayate  "},
                {"provincia": "Salta", "localidad": "cafayate"},
                {"provincia": "Jujuy", "localidad": "Tilcara   de   Arriba"},
                {"provincia": "", "localidad": ""},
            ]
        )

    assert zonas == [("Jujuy", "Tilcara de Arriba"), ("Salta", "Cafayate")]


def test_la_provincia_completa_absorbe_sus_localidades(app) -> None:
    with app.app_context():
        zonas = servicios.normalizar_zonas(
            [
                {"provincia": "Buenos Aires", "localidad": "Chascomús"},
                {"provincia": "Buenos Aires", "localidad": None},
                {"provincia": "Córdoba", "localidad": "Río Cuarto"},
            ]
        )

    assert zonas == [("Buenos Aires", None), ("Córdoba", "Río Cuarto")]


def test_una_provincia_fuera_de_la_lista_se_rechaza(app) -> None:
    with app.app_context(), pytest.raises(SolicitudInvalida) as error:
        servicios.normalizar_zonas([{"provincia": "Provincia de Narnia"}])

    assert "no es una provincia válida" in error.value.detalle["zonas"][0]


def test_una_localidad_sin_provincia_se_rechaza(app) -> None:
    with app.app_context(), pytest.raises(SolicitudInvalida) as error:
        servicios.normalizar_zonas([{"provincia": "", "localidad": "Chascomús"}])

    assert "indicá la provincia" in error.value.detalle["zonas"][0]


def test_una_ong_sin_zonas_no_se_puede_crear(app, base_de_datos: None) -> None:
    with app.app_context(), pytest.raises(SolicitudInvalida) as error:
        servicios.crear(nombre="ONG sin cobertura", tipo="ong", zonas=[])

    assert error.value.detalle["zonas"] == [servicios.MENSAJE_ONG_SIN_ZONAS]


def test_un_municipio_puede_crearse_sin_zonas(app, base_de_datos: None) -> None:
    with app.app_context():
        municipio = servicios.crear(nombre="Municipio de Lezama", tipo="municipio")

        assert municipio.zonas_de_cobertura == []


def test_editar_sin_zonas_conserva_la_cobertura_y_con_lista_la_reemplaza(
    app, base_de_datos: None
) -> None:
    with app.app_context():
        ong = _organizacion("Manos Unidas")
        servicios.editar(ong.id, nombre=ong.nombre, tipo="ong", contacto_telefono="221-555")
        assert [(z.provincia, z.localidad) for z in ong.zonas_de_cobertura] == [
            ("Buenos Aires", "Chascomús")
        ]

        servicios.editar(ong.id, nombre=ong.nombre, tipo="ong", zonas=[{"provincia": "Misiones"}])
        assert [(z.provincia, z.localidad) for z in ong.zonas_de_cobertura] == [("Misiones", None)]


# --- Unicidad y tipo --------------------------------------------------------------


def test_el_nombre_repetido_con_otra_caja_se_rechaza(app, base_de_datos: None) -> None:
    with app.app_context(), pytest.raises(ConflictoDeEstado):
        servicios.crear(nombre="MANOS UNIDAS", tipo="ong", zonas=[{"provincia": "Buenos Aires"}])


def test_no_se_cambia_el_tipo_de_una_organizacion_con_cuentas(app, base_de_datos: None) -> None:
    with app.app_context():
        ong = _organizacion("Cruz Solidaria")
        with pytest.raises(ConflictoDeEstado) as error:
            servicios.editar(ong.id, nombre=ong.nombre, tipo="municipio")

        assert "tipo" in error.value.detalle


def test_sin_cuentas_el_tipo_se_puede_cambiar(app, base_de_datos: None) -> None:
    with app.app_context():
        # Todos los municipios sembrados tienen un operador: se usa uno nuevo, sin cuentas.
        municipio = servicios.crear(
            nombre="Municipio de Lezama",
            tipo="municipio",
            zonas=[{"provincia": "Buenos Aires", "localidad": "Lezama"}],
        )
        servicios.editar(municipio.id, nombre=municipio.nombre, tipo="ong")

        assert servicios.obtener(municipio.id).tipo.value == "ong"
        assert servicios.obtener_inventario(municipio.id) is not None


# --- Inventario y verificacion ------------------------------------------------------


def test_la_ong_nueva_nace_con_inventario_vacio_y_verificada(app, base_de_datos: None) -> None:
    with app.app_context():
        ong = servicios.crear(
            nombre="Rescatistas del Delta",
            tipo="ong",
            identificador_nacional="30-11111111-1",
            zonas=[{"provincia": "Entre Ríos", "localidad": "Gualeguaychú"}],
        )

        inventario = servicios.obtener_inventario(ong.id)
        assert inventario is not None
        assert inventario.items == []
        assert ong.estado_verificacion.value == "verificada"


def test_un_municipio_nace_verificado_y_sin_inventario(app, base_de_datos: None) -> None:
    with app.app_context():
        municipio = servicios.crear(nombre="Municipio de Lezama", tipo="municipio")

        assert servicios.obtener_inventario(municipio.id) is None
        assert municipio.estado_verificacion.value == "verificada"


def test_editar_el_identificador_no_cambia_la_verificacion(app, base_de_datos: None) -> None:
    with app.app_context():
        ong = _organizacion("Manos Unidas")
        servicios.registrar_resultado_de_verificacion(ong.id, "rechazada")

        servicios.editar(ong.id, nombre=ong.nombre, tipo="ong", identificador_nacional="30-1-9")

        assert servicios.obtener(ong.id).estado_verificacion.value == "rechazada"


def test_un_estado_de_verificacion_inexistente_se_rechaza(app, base_de_datos: None) -> None:
    with app.app_context():
        ong = _organizacion("Manos Unidas")
        with pytest.raises(SolicitudInvalida):
            servicios.registrar_resultado_de_verificacion(ong.id, "aprobadisima")


# --- Busqueda, miembros y datos propios ---------------------------------------------


def test_el_texto_busca_tambien_en_localidad_e_identificador(app, base_de_datos: None) -> None:
    with app.app_context():
        por_localidad = [una.nombre for una in servicios.listar(texto="villarino")]
        por_identificador = [una.nombre for una in servicios.listar(texto="30-65432199")]

    assert por_localidad == ["Cruz Roja Argentina - Filial Bahía Blanca"]
    assert por_identificador == ["Manos Unidas"]


def test_el_filtro_por_provincia_trae_quien_la_cubre(app, base_de_datos: None) -> None:
    with app.app_context():
        nombres = [
            una.nombre for una in servicios.listar(provincia="Ciudad Autónoma de Buenos Aires")
        ]

    assert nombres == ["Cruz Solidaria"]


def test_los_miembros_son_las_cuentas_vinculadas(app, base_de_datos: None) -> None:
    with app.app_context():
        ong = _organizacion("Cruz Solidaria")
        emails = sorted(miembro["email"] for miembro in servicios.miembros(ong.id))

    assert emails == ["representante2@cruzsolidaria.test", "representante@cruzsolidaria.test"]


def test_un_miembro_solo_actualiza_contacto_y_cobertura(app, base_de_datos: None) -> None:
    with app.app_context():
        ong = _organizacion("Cruz Solidaria")
        servicios.editar_datos_propios(
            ong.id,
            contacto_telefono="0800-222-0000",
            zonas=[{"provincia": "Buenos Aires"}],
        )

        actualizada = servicios.obtener(ong.id)
        assert actualizada.nombre == "Cruz Solidaria"
        assert actualizada.contacto_telefono == "0800-222-0000"
        assert [(z.provincia, z.localidad) for z in actualizada.zonas_de_cobertura] == [
            ("Buenos Aires", None)
        ]


def test_una_ong_no_puede_quedarse_sin_cobertura_desde_sus_datos_propios(
    app, base_de_datos: None
) -> None:
    with app.app_context():
        ong = _organizacion("Cruz Solidaria")
        with pytest.raises(SolicitudInvalida):
            servicios.editar_datos_propios(ong.id, zonas=[])


def test_una_cuenta_sin_organizacion_no_tiene_organizacion_propia(app, base_de_datos: None) -> None:
    with app.app_context(), pytest.raises(RecursoNoEncontrado):
        servicios.obtener_propia(None)


# --- Cobertura nacional ---------------------------------------------------------------


def test_una_ong_nacional_no_necesita_zonas_y_las_ignora(app, base_de_datos: None) -> None:
    with app.app_context():
        ong = servicios.crear(
            nombre="Red Solidaria Argentina",
            tipo="ong",
            cobertura_nacional=True,
            zonas=[{"provincia": "Salta"}],
        )

        assert ong.cobertura_nacional is True
        assert ong.zonas_de_cobertura == []


def test_el_filtro_por_provincia_incluye_a_las_nacionales(app, base_de_datos: None) -> None:
    with app.app_context():
        servicios.crear(nombre="Red Solidaria Argentina", tipo="ong", cobertura_nacional=True)
        nombres = [una.nombre for una in servicios.listar(provincia="Tucumán")]

    assert nombres == ["Red Solidaria Argentina"]


def test_marcar_la_cobertura_nacional_borra_las_zonas(app, base_de_datos: None) -> None:
    with app.app_context():
        ong = _organizacion("Manos Unidas")
        servicios.editar(ong.id, nombre=ong.nombre, tipo="ong", cobertura_nacional=True)

        actualizada = servicios.obtener(ong.id)
        assert actualizada.cobertura_nacional is True
        assert actualizada.zonas_de_cobertura == []


def test_desmarcar_la_cobertura_nacional_exige_zonas_a_una_ong(app, base_de_datos: None) -> None:
    with app.app_context():
        ong = servicios.crear(nombre="Red Solidaria Argentina", tipo="ong", cobertura_nacional=True)

        with pytest.raises(SolicitudInvalida):
            servicios.editar(ong.id, nombre=ong.nombre, tipo="ong", cobertura_nacional=False)

        servicios.editar(
            ong.id,
            nombre=ong.nombre,
            tipo="ong",
            cobertura_nacional=False,
            zonas=[{"provincia": "Neuquén"}],
        )
        assert servicios.obtener(ong.id).cobertura_nacional is False


def test_sin_indicarla_la_cobertura_nacional_se_conserva(app, base_de_datos: None) -> None:
    with app.app_context():
        ong = servicios.crear(nombre="Red Solidaria Argentina", tipo="ong", cobertura_nacional=True)
        servicios.editar(ong.id, nombre=ong.nombre, tipo="ong", contacto_telefono="0800")
        servicios.editar_datos_propios(ong.id, contacto_telefono="0810")

        assert servicios.obtener(ong.id).cobertura_nacional is True


# --- Varias localidades separadas por comas ---------------------------------------------


def test_las_localidades_separadas_por_comas_son_zonas_propias(app) -> None:
    with app.app_context():
        zonas = servicios.normalizar_zonas(
            [{"provincia": "Buenos Aires", "localidad": "La Plata, Berisso,   Los  Hornos"}]
        )

    assert zonas == [
        ("Buenos Aires", "Berisso"),
        ("Buenos Aires", "La Plata"),
        ("Buenos Aires", "Los Hornos"),
    ]


def test_las_comas_sobrantes_se_ignoran(app) -> None:
    with app.app_context():
        zonas = servicios.normalizar_zonas(
            [{"provincia": "Salta", "localidad": ", Cafayate,, Cachi ,"}]
        )

    assert zonas == [("Salta", "Cachi"), ("Salta", "Cafayate")]


def test_un_campo_con_solo_comas_es_un_error_y_no_toda_la_provincia(app) -> None:
    with app.app_context(), pytest.raises(SolicitudInvalida) as error:
        servicios.normalizar_zonas([{"provincia": "Salta", "localidad": " , ,, "}])

    assert "no tiene ninguna localidad" in error.value.detalle["zonas"][0]


def test_las_repetidas_se_descartan_en_la_misma_fila_y_entre_filas(app) -> None:
    with app.app_context():
        zonas = servicios.normalizar_zonas(
            [
                {"provincia": "Buenos Aires", "localidad": "La Plata, la plata, Berisso"},
                {"provincia": "Buenos Aires", "localidad": "BERISSO, Ensenada"},
            ]
        )

    assert zonas == [
        ("Buenos Aires", "Berisso"),
        ("Buenos Aires", "Ensenada"),
        ("Buenos Aires", "La Plata"),
    ]


def test_la_provincia_completa_absorbe_las_localidades_separadas_por_comas(app) -> None:
    with app.app_context():
        zonas = servicios.normalizar_zonas(
            [
                {"provincia": "Buenos Aires", "localidad": "La Plata, Berisso"},
                {"provincia": "Buenos Aires", "localidad": ""},
            ]
        )

    assert zonas == [("Buenos Aires", None)]


def test_cada_localidad_separada_respeta_el_largo_maximo(app) -> None:
    larga = "X" * (servicios.MAXIMO_DE_LOCALIDAD + 1)
    with app.app_context(), pytest.raises(SolicitudInvalida) as error:
        servicios.normalizar_zonas([{"provincia": "Chaco", "localidad": f"Resistencia, {larga}"}])

    assert len(error.value.detalle["zonas"]) == 1
    assert "supera los 150 caracteres" in error.value.detalle["zonas"][0]


def test_el_campo_de_localidades_tiene_un_largo_maximo(app) -> None:
    texto = ", ".join(["Localidad"] * 200)
    with app.app_context(), pytest.raises(SolicitudInvalida) as error:
        servicios.normalizar_zonas([{"provincia": "Chaco", "localidad": texto}])

    assert "admite hasta" in error.value.detalle["zonas"][0]


def test_hay_un_tope_de_zonas_por_organizacion(app) -> None:
    filas = [
        {"provincia": "Chaco", "localidad": ", ".join(f"L{fila}-{n}" for n in range(50))}
        for fila in range(5)
    ]
    with app.app_context(), pytest.raises(SolicitudInvalida) as error:
        servicios.normalizar_zonas(filas)

    assert "el máximo es 200" in error.value.detalle["zonas"][0]


def test_una_localidad_que_no_es_texto_se_rechaza(app) -> None:
    with app.app_context(), pytest.raises(SolicitudInvalida) as error:
        servicios.normalizar_zonas([{"provincia": "Chaco", "localidad": 123}])

    assert "tienen que ser texto" in error.value.detalle["zonas"][0]


def test_las_zonas_se_reagrupan_por_provincia_para_el_formulario(app) -> None:
    with app.app_context():
        filas = servicios.zonas_agrupadas_por_provincia(
            [
                ("Buenos Aires", "Berisso"),
                ("Buenos Aires", "La Plata"),
                ("Ciudad Autónoma de Buenos Aires", None),
            ]
        )

    assert filas == [
        {"provincia": "Buenos Aires", "localidad": "Berisso, La Plata"},
        {"provincia": "Ciudad Autónoma de Buenos Aires", "localidad": None},
    ]
