from __future__ import annotations

from app.core.integraciones.bonita.api import instanciar_proceso


def iniciar_gestion(emergencia_id: int) -> str:
    return instanciar_proceso(
        {
            "emergenciaIdInput": str(emergencia_id),
        }
    )