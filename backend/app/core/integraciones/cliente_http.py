"""Politica comun de las llamadas salientes hacia Bonita y la API Nacional.

ALCANCE: este modulo es andamiaje. La epica del esqueleto ejecutable fija la politica y deja
las constantes en un solo lugar; la implementacion del cliente HTTP pertenece a la epica de
integraciones, que ademas tendra que elegir la libreria HTTP, agregarla a `pyproject.toml`
con version exacta y sumarla a la tabla de stack del README.

La politica es la de docs/contratos/errores.md y es identica para los dos destinos.

Reglas que la implementacion tiene que respetar
-----------------------------------------------
- Se reintenta solo ante 5xx, timeout o error de red, y solo en operaciones idempotentes.
  Nunca ante un 4xx.
- Los POST que comprometen recursos viajan con cabecera `Idempotency-Key`.
- La instanciacion de proceso en Bonita (integracion 3) NO es idempotente y no tiene clave
  propia: ante timeout se reporta el error en lugar de reintentar.
- Distincion obligatoria, evaluada como criterio de aceptacion:
  agotar los reintentos -> 503 SERVICIO_EXTERNO_NO_DISPONIBLE (invita a reintentar);
  el externo respondio 4xx -> 422 SISTEMA_EXTERNO_RECHAZO (no invita a reintentar).
- Cada intento emite un evento `llamada_saliente` con
  `app.core.logging.registrar_llamada_saliente()`, tanto si salio bien como si no.
- El `id_correlacion` de la solicitud entrante viaja en la cabecera `X-Correlation-Id` de
  toda llamada saliente.
- Antes de loguear cualquier cabecera o cuerpo se pasa por `app.core.logging.redactar()` y
  `redactar_cabeceras()`. El cuerpo completo no se loguea por defecto.
- `endpoint` se loguea normalizado (`/emergencias/{id}/ofertas`), nunca con valores del
  dominio ya sustituidos.
"""

from __future__ import annotations
import time
import random
import httpx
from app.core.logging import registrar_llamada_saliente, id_correlacion_actual
from app.core.errores import SistemaExternoRechazo, ServicioExternoNoDisponible

TIMEOUT_CONEXION_S = 3
TIMEOUT_LECTURA_S = 10

# Un intento original mas dos reintentos.
INTENTOS_TOTALES = 3

# Backoff exponencial entre intentos, en milisegundos: 500 -> 1000 -> 2000.
BACKOFF_BASE_MS = 500
BACKOFF_FACTOR = 2

# Proporcion de jitter aleatorio que se aplica a cada espera, hacia arriba y hacia abajo.
JITTER = 0.20

CABECERA_CORRELACION = "X-Correlation-Id"
CABECERA_IDEMPOTENCIA = "Idempotency-Key"

COMPONENTE_BONITA = "bonita"
COMPONENTE_API_NACIONAL = "api_nacional"


def espera_ms(intento: int) -> int:
    """Milisegundos a esperar antes del intento indicado (el primero no espera).

    Devuelve la espera sin jitter; la implementacion le aplica el +/- JITTER al usarla.
    """
    if intento <= 1:
        return 0
    return BACKOFF_BASE_MS * (BACKOFF_FACTOR ** (intento - 2))

def ejecutar_solicitud(
    cliente: httpx.Client,
    *,
    componente: str,
    metodo: str,
    endpoint_normalizado: str,
    url: str,
    idempotente: bool,
    headers: dict[str, str] | None = None,
    **kwargs,
) -> httpx.Response:
    id_correlacion = id_correlacion_actual()

    cabeceras = dict(headers or {})
    cabeceras[CABECERA_CORRELACION] = id_correlacion

    cantidad_intentos = INTENTOS_TOTALES if idempotente else 1

    for intento in range(1, cantidad_intentos + 1):
        espera = espera_ms(intento)

        if espera > 0:
            variacion = espera * JITTER
            espera_con_jitter = random.uniform(
                espera - variacion,
                espera + variacion,
            )
            time.sleep(espera_con_jitter / 1000)

        inicio = time.perf_counter()

        try:
            respuesta = cliente.request(
                method=metodo,
                url=url,
                headers=cabeceras,
                timeout=httpx.Timeout(
                    connect=TIMEOUT_CONEXION_S,
                    read=TIMEOUT_LECTURA_S,
                    write=TIMEOUT_LECTURA_S,
                    pool=TIMEOUT_CONEXION_S,
                ),
                **kwargs,
            )

        except httpx.RequestError:
            duracion_ms = int((time.perf_counter() - inicio) * 1000)

            registrar_llamada_saliente(
                componente_destino=componente,
                metodo=metodo,
                endpoint=endpoint_normalizado,
                codigo_estado=None,
                duracion_ms=duracion_ms,
                intento=intento,
                resultado="error",
                id_correlacion=id_correlacion,
            )

            if intento == cantidad_intentos:
                raise ServicioExternoNoDisponible(
                    detalle={"componente": componente}
                )

            continue

        duracion_ms = int((time.perf_counter() - inicio) * 1000)

        registrar_llamada_saliente(
            componente_destino=componente,
            metodo=metodo,
            endpoint=endpoint_normalizado,
            codigo_estado=respuesta.status_code,
            duracion_ms=duracion_ms,
            intento=intento,
            resultado="exito" if respuesta.is_success else "error",
            id_correlacion=id_correlacion,
        )

        if 400 <= respuesta.status_code < 500:
            raise SistemaExternoRechazo(
                detalle={
                    "componente": componente,
                    "codigo_estado": respuesta.status_code,
                }
            )

        if respuesta.status_code >= 500:
            if intento == cantidad_intentos:
                raise ServicioExternoNoDisponible(
                    detalle={
                        "componente": componente,
                        "codigo_estado": respuesta.status_code,
                    }
                )

            continue

        return respuesta

    raise ServicioExternoNoDisponible(
        detalle={"componente": componente}
    )