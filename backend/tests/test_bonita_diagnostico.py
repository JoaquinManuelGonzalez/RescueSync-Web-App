"""`flask bonita-diagnostico`: que encuentra y que pista da ante cada problema de Bonita.

Se reemplaza `ejecutar_solicitud` por un Bonita falso que responde por endpoint, con la forma de
la REST API real.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.core.errores import ServicioExternoNoDisponible, SistemaExternoRechazo
from app.core.integraciones.bonita import diagnostico, sesion
from app.core.integraciones.bonita.diagnostico import Resultado

ROL_MEMBER = "1"
MUNICIPAL, COORDINADOR = "Empleado municipal", "Empleado centro coordinador"


class BonitaFalso:
    def __init__(self) -> None:
        self.responde = True
        self.logins_validos = {sesion.BONITA_USER, "operador@chascomus.test"}
        self.procesos: list[dict[str, Any]] = [
            {"id": "77", "activationState": "ENABLED", "deploymentDate": "2026-11-14 12:28:01.5"}
        ]
        self.actores = [{"id": "10", "name": MUNICIPAL}, {"id": "11", "name": COORDINADOR}]
        # Ambos actores mapeados al rol member: todos los que lo tengan son candidatos.
        self.miembros = {
            "10": [{"user_id": "-1", "role_id": ROL_MEMBER, "group_id": "-1"}],
            "11": [{"user_id": "-1", "role_id": ROL_MEMBER, "group_id": "-1"}],
        }
        self.usuarios = {"operador@chascomus.test": "5"}
        self.membresias = {
            "4": [{"role_id": ROL_MEMBER, "group_id": "2"}],
            "5": [{"role_id": ROL_MEMBER, "group_id": "2"}],
        }

    def __call__(self, cliente: httpx.Client, *, endpoint_normalizado: str, **kwargs):
        if not self.responde:
            raise ServicioExternoNoDisponible(detalle={"componente": "bonita"})
        filtros = dict(
            valor.split("=", 1) for clave, valor in kwargs.get("params", []) if clave == "f"
        )
        if endpoint_normalizado == "/":
            return httpx.Response(200)
        if endpoint_normalizado == "/loginservice":
            if kwargs["data"]["username"] not in self.logins_validos:
                raise SistemaExternoRechazo(detalle={"componente": "bonita", "codigo_estado": 401})
            cliente.cookies.set(sesion.NOMBRE_COOKIE_TOKEN, "token")
            return httpx.Response(204)
        respuestas = {
            "/API/bpm/process": lambda: self.procesos,
            "/API/bpm/actor": lambda: self.actores,
            "/API/bpm/actorMember": lambda: self.miembros[filtros["actor_id"]],
            "/API/system/session/unusedid": lambda: {"user_id": "4"},
            "/API/identity/membership": lambda: self.membresias.get(filtros["user_id"], []),
            "/API/identity/user": lambda: (
                [{"id": self.usuarios[filtros["userName"]]}]
                if filtros["userName"] in self.usuarios
                else []
            ),
        }
        return httpx.Response(200, json=respuestas[endpoint_normalizado]())


@pytest.fixture
def bonita(monkeypatch) -> BonitaFalso:
    falso = BonitaFalso()
    monkeypatch.setattr(diagnostico, "ejecutar_solicitud", falso)
    return falso


def _por_nombre(chequeos) -> dict[str, diagnostico.Chequeo]:
    return {chequeo.nombre: chequeo for chequeo in chequeos}


def test_con_todo_en_orden_cada_chequeo_da_bien(bonita) -> None:
    chequeos = diagnostico.diagnosticar({MUNICIPAL: ["operador@chascomus.test"]})

    assert [chequeo.resultado for chequeo in chequeos] == [Resultado.OK] * len(chequeos)
    nombres = [chequeo.nombre for chequeo in chequeos]
    assert nombres[:3] == [
        "Conexión",
        f"Login de {sesion.BONITA_USER}",
        "Proceso RescueSync 1.0",
    ]
    assert "2026-11-14 12:28" in chequeos[2].detalle, "la fecha delata un despliegue viejo"
    assert f"Actor «{MUNICIPAL}»" in nombres
    assert "Usuario operador@chascomus.test" in nombres


def test_sin_bonita_solo_se_informa_la_conexion(bonita) -> None:
    bonita.responde = False

    chequeos = diagnostico.diagnosticar()

    assert len(chequeos) == 1
    assert chequeos[0].resultado is Resultado.ERROR
    assert "host.docker.internal" in chequeos[0].pista


def test_un_401_del_usuario_tecnico_apunta_a_desplegar_la_organizacion(bonita) -> None:
    bonita.logins_validos = set()

    chequeos = diagnostico.diagnosticar()

    login = chequeos[-1]
    assert login.resultado is Resultado.ERROR
    assert "401" in login.detalle
    assert "ACME.xml" in login.pista and "Desplegar" in login.pista


def test_un_proceso_no_desplegado_lo_indica_y_corta(bonita) -> None:
    bonita.procesos = []

    chequeos = diagnostico.diagnosticar()

    assert chequeos[-1].nombre == "Proceso RescueSync 1.0"
    assert chequeos[-1].resultado is Resultado.ERROR
    assert "Ejecutar" in chequeos[-1].pista


def test_un_proceso_deshabilitado_es_un_error(bonita) -> None:
    bonita.procesos[0]["activationState"] = "DISABLED"

    proceso = _por_nombre(diagnostico.diagnosticar())["Proceso RescueSync 1.0"]

    assert proceso.resultado is Resultado.ERROR


def test_un_actor_sin_mapeo_o_sin_el_usuario_tecnico_es_un_error(bonita) -> None:
    bonita.miembros["10"] = []
    bonita.miembros["11"] = [{"user_id": "99", "role_id": "-1", "group_id": "-1"}]

    chequeos = _por_nombre(diagnostico.diagnosticar())

    assert chequeos[f"Actor «{MUNICIPAL}»"].resultado is Resultado.ERROR
    assert "nadie" in chequeos[f"Actor «{MUNICIPAL}»"].detalle
    assert chequeos[f"Actor «{COORDINADOR}»"].resultado is Resultado.ERROR
    assert "Actor mapping" in chequeos[f"Actor «{COORDINADOR}»"].pista


def test_el_tecnico_es_candidato_por_mapeo_directo(bonita) -> None:
    bonita.miembros["10"] = [{"user_id": "4", "role_id": "-1", "group_id": "-1"}]

    actor = _por_nombre(diagnostico.diagnosticar())[f"Actor «{MUNICIPAL}»"]

    assert actor.resultado is Resultado.OK


def test_un_usuario_de_la_app_que_no_existe_en_bonita_es_solo_un_aviso(bonita) -> None:
    chequeos = diagnostico.diagnosticar({COORDINADOR: ["coordinador@otra.test"]})

    usuario = _por_nombre(chequeos)["Usuario coordinador@otra.test"]
    assert usuario.resultado is Resultado.AVISO
    assert sesion.BONITA_USER in usuario.detalle
    assert all(chequeo.resultado is not Resultado.ERROR for chequeo in chequeos)


def test_un_usuario_que_entra_pero_no_es_candidato_de_su_actor_es_un_aviso(bonita) -> None:
    bonita.membresias["5"] = []

    chequeos = diagnostico.diagnosticar({MUNICIPAL: ["operador@chascomus.test"]})

    usuario = _por_nombre(chequeos)["Usuario operador@chascomus.test"]
    assert usuario.resultado is Resultado.AVISO
    assert MUNICIPAL in usuario.detalle


def test_el_comando_sale_con_error_si_algun_chequeo_falla(app, base_de_datos, bonita) -> None:
    bonita.logins_validos = set()

    resultado = app.test_cli_runner().invoke(args=["bonita-diagnostico"])

    assert resultado.exit_code == 1
    assert "✗ Login de" in resultado.output
    assert "→" in resultado.output


def test_el_comando_lista_los_chequeos_y_sale_bien(app, base_de_datos, bonita) -> None:
    resultado = app.test_cli_runner().invoke(args=["bonita-diagnostico"])

    assert resultado.exit_code == 0, resultado.output
    assert "✓ Conexión" in resultado.output
