# Contrato de errores

Este documento define el formato único de error que devuelven todos los endpoints de la
aplicación web de RescueSync, la tabla de correspondencia entre códigos HTTP y códigos internos,
y la política de reintentos frente a los sistemas externos (Bonita y la API Nacional). Es el
contrato que referencia el ADR-006.

## 1. Envelope único de error

Todo error de la aplicación, sin excepción, se devuelve con la misma estructura JSON, con el
objeto de nivel superior `error` y cinco campos obligatorios: `codigo`, `mensaje`, `detalle`,
`timestamp` e `id_correlacion`. Esto vale para todo cliente que no sea un navegador navegando
la interfaz; cómo se le presenta el mismo error a una persona está en la sección 2.1.

| Campo | Tipo | Descripción |
|---|---|---|
| `codigo` | string | Código interno estable, en mayúsculas con guion bajo, tomado de la tabla de la sección 2 |
| `mensaje` | string | Mensaje pensado para mostrarse al usuario final, en español, sin detalles técnicos internos |
| `detalle` | array u objeto (puede ser `null`) | Información adicional estructurada: campos inválidos, motivo devuelto por un sistema externo, etc. |
| `timestamp` | string, ISO-8601 UTC | Momento exacto en que se generó el error |
| `id_correlacion` | string (UUID) | Identificador que permite rastrear la solicitud en los logs de los tres componentes, ver `docs/contratos/logging.md` |

```json
{
  "error": {
    "codigo": "OFERTA_FUERA_DE_VENTANA",
    "mensaje": "La ventana de recepción de ofertas está cerrada.",
    "detalle": [{"campo": "convocatoria_id", "motivo": "cerrada el 2026-10-05T18:00:00Z"}],
    "timestamp": "2026-10-05T18:04:11.482Z",
    "id_correlacion": "8f3a1c22-5d6e-4f19-a0b1-2c3d4e5f6a7b"
  }
}
```

### 1.1 Ejemplos del dominio

**Validación de formulario** (alta de emergencia con campos faltantes):

```json
{
  "error": {
    "codigo": "SOLICITUD_INVALIDA",
    "mensaje": "El formulario tiene campos inválidos o incompletos.",
    "detalle": [
      {"campo": "nivel_de_gravedad", "motivo": "es obligatorio"},
      {"campo": "ubicacion", "motivo": "debe tener entre 5 y 200 caracteres"}
    ],
    "timestamp": "2026-10-01T13:10:44.001Z",
    "id_correlacion": "1a2b3c4d-1111-4a2b-8c3d-9f0e1d2c3b4a"
  }
}
```

**Permiso denegado por rol** (un Representante de ONG intenta adjudicar una convocatoria):

```json
{
  "error": {
    "codigo": "PERMISO_DENEGADO",
    "mensaje": "Tu rol no tiene permiso para realizar esta acción.",
    "detalle": {"accion": "adjudicacion.crear", "rol_actual": "representante_ong"},
    "timestamp": "2026-10-03T09:22:15.730Z",
    "id_correlacion": "2b3c4d5e-2222-4b3c-9d4e-0a1b2c3d4e5f"
  }
}
```

**Oferta cargada fuera de la ventana temporal** (la ONG carga una oferta después del cierre):

```json
{
  "error": {
    "codigo": "REGLA_DE_NEGOCIO_INCUMPLIDA",
    "mensaje": "La ventana de recepción de ofertas está cerrada.",
    "detalle": [{"campo": "convocatoria_id", "motivo": "cerrada el 2026-10-05T18:00:00Z"}],
    "timestamp": "2026-10-05T18:04:11.482Z",
    "id_correlacion": "8f3a1c22-5d6e-4f19-a0b1-2c3d4e5f6a7b"
  }
}
```

**API Nacional caída** (se agotan los reintentos al registrar un compromiso de recursos):

```json
{
  "error": {
    "codigo": "SERVICIO_EXTERNO_NO_DISPONIBLE",
    "mensaje": "El Sistema Nacional no responde en este momento. La operación no se registró; reintentá en unos minutos.",
    "detalle": {"componente": "api_nacional", "intentos_realizados": 3},
    "timestamp": "2026-10-06T11:47:03.256Z",
    "id_correlacion": "3c4d5e6f-3333-4c5d-8e0f-1a2b3c4d5e6f"
  }
}
```

## 2. Tabla de códigos HTTP y códigos internos

| HTTP | Código interno | Cuándo se usa |
|---|---|---|
| 400 | `SOLICITUD_INVALIDA` | El JSON o el formulario recibido está mal formado o incompleto |
| 401 | `NO_AUTENTICADO` | No hay sesión activa, o el token de servicio (por ejemplo `BONITA_CALLBACK_TOKEN`) es inválido o falta |
| 403 | `PERMISO_DENEGADO` | El rol del usuario autenticado no habilita la acción solicitada (RBAC) |
| 404 | `RECURSO_NO_ENCONTRADO` | La entidad referenciada no existe |
| 409 | `CONFLICTO_DE_ESTADO` | La entidad no admite la transición solicitada (por ejemplo, la emergencia ya fue adjudicada) |
| 422 | `REGLA_DE_NEGOCIO_INCUMPLIDA` | Falla una validación de dominio propia (por ejemplo, oferta fuera de la ventana temporal) |
| 422 | `SISTEMA_EXTERNO_RECHAZO` | La API Nacional o Bonita respondieron con un 4xx: la solicitud fue evaluada y rechazada |
| 500 | `ERROR_INTERNO` | Excepción no contemplada dentro de la propia aplicación |
| 502 | `RESPUESTA_EXTERNA_INVALIDA` | El sistema externo respondió con un cuerpo ilegible o con un formato inesperado |
| 503 | `SERVICIO_EXTERNO_NO_DISPONIBLE` | El sistema externo respondió 5xx, o no respondió, tras agotar los reintentos |
| 504 | `TIEMPO_DE_ESPERA_AGOTADO` | El sistema externo no respondió dentro del tiempo de espera configurado |

### 2.1 Respuesta según el cliente

La misma ruta atiende a la interfaz y a los clientes JSON (tests, `curl`, un `fetch`, Bonita).
Quién es quién lo decide `app.core.vistas.pide_json()` a partir de la cabecera `Accept`:

- `Accept` con `text/html` por delante de `application/json` (lo que manda un navegador al
  navegar) ⇒ **navegador**.
- Cuerpo JSON, `Accept: application/json`, `Accept: */*` o sin `Accept` ⇒ **cliente JSON**, que
  recibe el envelope de la sección 1 exactamente como siempre.

Al navegador el envelope no le sirve: una persona no puede leer JSON crudo. El mismo error, con
el **mismo código HTTP y el mismo mensaje**, se traduce así (`app/core/errores.py`), en este
orden:

| Situación | Qué ve el navegador |
|---|---|
| Falla un formulario cuya vista declaró `@plantilla_ante_error` (400, 401, 403, 409, 422 en un POST) | El mismo formulario, con lo cargado, cada mensaje de `detalle` junto a su campo y el `mensaje` como alerta arriba. El código HTTP es el del error |
| `NO_AUTENTICADO` (sin sesión o sesión vencida) | Redirect a `/sesion/ingreso` con el mensaje como aviso. En un GET, con `?next=` para volver a la pantalla pedida después de ingresar |
| `CONFLICTO_DE_ESTADO` por contraseña pendiente de cambio | Redirect a `/sesion/contrasena` con el aviso |
| Token CSRF faltante o vencido | Redirect a la pantalla de origen con el aviso "El formulario venció…", para volver a enviarlo |
| Cualquier otro (403, 404, 405, 500, 502, 503, 504…) | La página `errores/error.html`: título legible, `mensaje` e `id_correlacion` como "código de referencia" |

El `id_correlacion` sigue siendo el mismo que queda en los logs, así que un "código de
referencia" que dicta una persona alcanza para encontrar la solicitud. Si la página de error no
se puede renderizar (por ejemplo, porque lo que falla es la base de datos), la respuesta cae al
envelope JSON.

## 3. Política de reintentos ante sistemas externos

Toda llamada de la aplicación web hacia un sistema externo (Bonita o API Nacional) sigue la misma
política de tiempos de espera y reintentos, implementada en los clientes de
`core/integraciones/`.

| Parámetro | Valor |
|---|---|
| Timeout de conexión | 3 segundos |
| Timeout de lectura | 10 segundos |
| Intentos totales | 3 (1 intento original + 2 reintentos) |
| Backoff | Exponencial: 500 ms → 1 s → 2 s |
| Jitter | ± 20 % sobre cada espera de backoff |
| Condición para reintentar | Respuesta 5xx, timeout, o error de red (conexión rechazada, DNS, etc.) |
| Condición para NO reintentar | Cualquier respuesta 4xx |
| Alcance de los reintentos | Solo operaciones idempotentes |

Reglas de aplicación:

- **Solo se reintenta ante 5xx, timeout o error de red, y solo en operaciones idempotentes.** Una
  operación de solo lectura (por ejemplo, consultar el estado de una tarea en Bonita) siempre es
  candidata a reintento.
- **Los `POST` de compromiso de recursos llevan clave de idempotencia** (un identificador único
  generado por la aplicación web y enviado en un encabezado, por ejemplo
  `Idempotency-Key`), de modo que puedan reintentarse de forma segura ante un timeout o un 5xx sin
  riesgo de comprometer el mismo recurso dos veces.
- **Los 4xx nunca se reintentan.** Un 4xx significa que el sistema externo evaluó la solicitud y
  la rechazó por su contenido; reintentar con el mismo contenido produciría el mismo rechazo.
- Agotados los tres intentos sin éxito ante un 5xx, timeout o error de red, la aplicación web
  responde al usuario con `503 SERVICIO_EXTERNO_NO_DISPONIBLE`.

### 3.1 Distinción obligatoria: servicio no disponible vs. solicitud rechazada

Esta distinción es un criterio de aceptación evaluado explícitamente y debe quedar inconfundible
tanto en el código como en el mensaje que ve el usuario.

| | Servicio no disponible | Solicitud rechazada |
|---|---|---|
| Código HTTP | 503 | 422 |
| Código interno | `SERVICIO_EXTERNO_NO_DISPONIBLE` | `SISTEMA_EXTERNO_RECHAZO` |
| Causa | El sistema externo no respondió, respondió 5xx, o hubo timeout/error de red, incluso tras agotar los reintentos | El sistema externo respondió con un 4xx: evaluó la solicitud y la rechazó por su contenido |
| ¿Se registró la operación? | No | No (fue rechazada explícitamente) |
| Mensaje al usuario | «El Sistema Nacional no responde en este momento. La operación no se registró; reintentá en unos minutos.» | El motivo devuelto por el sistema externo, sin invitar a reintentar |
| ¿Invita a reintentar? | Sí | No |

Nunca se debe mostrar el mensaje de "no disponible" ante un rechazo explícito del sistema
externo, ni viceversa: son situaciones semánticamente distintas (una es una falla de
infraestructura o disponibilidad, la otra es una decisión de negocio del sistema externo) y el
usuario debe poder distinguir si tiene sentido reintentar o si debe corregir algo.

## 4. La misma política aplicada a Bonita

La política de timeouts, reintentos y backoff de la sección 3 aplica igual a las llamadas hacia
Bonita (integraciones 3 y 5 de `docs/arquitectura/componentes.md`), con los mismos valores:

| Parámetro | Valor aplicado a Bonita |
|---|---|
| Timeout de conexión | 3 segundos |
| Timeout de lectura | 10 segundos |
| Intentos totales | 3 (1 intento original + 2 reintentos) |
| Backoff | Exponencial: 500 ms → 1 s → 2 s, con jitter ± 20 % |
| Se reintenta ante | 5xx, timeout, error de red, en operaciones idempotentes (por ejemplo, consultar el estado de una tarea) |
| No se reintenta ante | 4xx (por ejemplo, sesión de Bonita expirada sin renovación exitosa, variables de proceso inválidas) |
| Código ante caída de Bonita | 503 `SERVICIO_EXTERNO_NO_DISPONIBLE` |
| Código ante rechazo de Bonita | 422 `SISTEMA_EXTERNO_RECHAZO` |

La instanciación de un proceso (integración 3, disparada al registrar una emergencia) no es
idempotente por naturaleza, por lo que su cliente debe generar y enviar una clave de idempotencia
propia antes de considerarla reintentable; sin esa clave, ante un timeout se prefiere reportar el
error al usuario en lugar de reintentar y arriesgar una doble instanciación del proceso.
