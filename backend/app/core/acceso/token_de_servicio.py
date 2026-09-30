from __future__ import annotations

import hmac
import os

from flask import request

from app.core.errores import NoAutenticado

_ESQUEMA_BEARER = "Bearer"


def _token_bonita_configurado() -> str:
    token = os.environ.get("BONITA_CALLBACK_TOKEN", "")

    if not token:
        raise RuntimeError(
            "BONITA_CALLBACK_TOKEN no está configurado."
        )

    return token


def validar_token_bonita() -> None:
    authorization = request.headers.get("Authorization", "")

    esquema, separador, token = authorization.partition(" ")

    if (
        not separador
        or esquema.lower() != _ESQUEMA_BEARER.lower()
        or not token
        or not hmac.compare_digest(
            token,
            _token_bonita_configurado(),
        )
    ):
        raise NoAutenticado()