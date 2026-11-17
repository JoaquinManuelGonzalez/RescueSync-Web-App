"""Ids UUID de las entidades: generación, lectura desde formularios y JSON, y cómo se muestran."""

from __future__ import annotations

import uuid

import pytest
from flask_wtf import FlaskForm
from werkzeug.datastructures import MultiDict

from app.core.identificadores import exigir_id, nuevo_id, parsear_id
from app.core.interfaz.formularios import CampoId
from app.core.interfaz.plantillas import SIN_DATO, id_corto

ID = uuid.UUID("0193f4a2-7c1e-7b5d-9a3f-2e8c4b6d1a01")


def test_nuevo_id_es_uuid7_y_ordena_por_fecha_de_alta():
    ids = [nuevo_id() for _ in range(50)]

    assert all(identificador.version == 7 for identificador in ids)
    # Ordenar por id sigue siendo ordenar por alta, como con los enteros.
    assert ids == sorted(ids)


@pytest.mark.parametrize(
    "valor",
    [ID, str(ID), str(ID).upper(), f"  {ID}  ", ID.hex],
    ids=["uuid", "texto", "mayusculas", "con-espacios", "sin-guiones"],
)
def test_parsear_id_acepta_las_formas_de_un_uuid(valor):
    assert parsear_id(valor) == ID


@pytest.mark.parametrize("valor", [None, "", "1", 1, 1.5, "emergencia-42", [str(ID)]])
def test_parsear_id_devuelve_none_si_no_es_un_uuid(valor):
    # Un entero es justo lo que hay que rechazar: se repite entre las webs que usan la misma API.
    assert parsear_id(valor) is None


def test_exigir_id_levanta_value_error_para_wtforms():
    assert exigir_id(str(ID)) == ID
    with pytest.raises(ValueError, match="identificador"):
        exigir_id("7")


class _Formulario(FlaskForm):
    organizacion_id = CampoId("Organización")


@pytest.mark.parametrize(
    ("enviado", "esperado"),
    [(str(ID), ID), ("", None)],
    ids=["uuid", "vacio"],
)
def test_campo_id_convierte_lo_que_llega_del_formulario(app, enviado, esperado):
    with app.test_request_context():
        formulario = _Formulario(
            formdata=MultiDict({"organizacion_id": enviado}), meta={"csrf": False}
        )

        assert formulario.validate()
        assert formulario.organizacion_id.data == esperado


def test_campo_id_marca_error_si_el_formulario_trae_otra_cosa(app):
    with app.test_request_context():
        formulario = _Formulario(formdata=MultiDict({"organizacion_id": "3"}), meta={"csrf": False})

        assert not formulario.validate()
        assert formulario.errors == {"organizacion_id": [CampoId.MENSAJE_INVALIDO]}


def test_campo_id_tambien_lee_el_cuerpo_json(app):
    with app.test_request_context():
        valido = _Formulario(data={"organizacion_id": str(ID)}, meta={"csrf": False})
        invalido = _Formulario(data={"organizacion_id": 3}, meta={"csrf": False})

        assert valido.validate() and valido.organizacion_id.data == ID
        assert not invalido.validate()


def test_id_corto_muestra_el_final_aleatorio_del_uuid():
    assert id_corto(ID) == "4B6D1A01"
    assert id_corto(str(ID)) == "4B6D1A01"
    assert id_corto(None) == SIN_DATO
