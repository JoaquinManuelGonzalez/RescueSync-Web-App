# Contrato de logging

Este documento define el formato de los logs de la aplicación web de RescueSync, los campos
obligatorios de toda llamada saliente hacia Bonita o la API Nacional, qué información nunca se
registra, y el mecanismo de correlación que permite rastrear una operación a través de los tres
componentes del sistema. Es el contrato que referencia el ADR-006.

## 1. Formato

Cada evento de log es una única línea en formato JSON (`JSON Lines`, un objeto JSON por línea, sin
saltos de línea internos). El destino de todos los logs es la salida estándar (`stdout`) del
contenedor de la aplicación web; no se escriben archivos de log dentro del contenedor. La
recolección y persistencia de esos logs (agregador, almacenamiento externo) queda fuera del
alcance de la aplicación y es responsabilidad del entorno de despliegue.

## 2. Campos obligatorios de toda llamada saliente

Toda llamada de la aplicación web hacia Bonita o hacia la API Nacional genera exactamente un
evento de log con estos campos, tanto si la llamada tuvo éxito como si terminó en error:

| Campo | Tipo | Obligatorio | Ejemplo |
|---|---|---|---|
| `timestamp` | string, ISO-8601 UTC | Sí | `"2026-10-05T18:04:09.112Z"` |
| `nivel` | string | Sí | `"INFO"` |
| `evento` | string, constante `"llamada_saliente"` | Sí | `"llamada_saliente"` |
| `componente_destino` | string, `"bonita"` o `"api_nacional"` | Sí | `"api_nacional"` |
| `metodo` | string, verbo HTTP | Sí | `"POST"` |
| `endpoint` | string, ruta normalizada, sin datos de la query string | Sí | `"/recursos/compromisos"` |
| `codigo_estado` | entero, código HTTP recibido (`null` si no hubo respuesta) | Sí | `503` |
| `duracion_ms` | entero, duración de la llamada en milisegundos | Sí | `2140` |
| `intento` | entero, número de intento dentro de la política de reintentos (1, 2 o 3) | Sí | `2` |
| `resultado` | string, `"exito"` o `"error"` | Sí | `"error"` |
| `id_correlacion` | string (UUID) | Sí | `"8f3a1c22-5d6e-4f19-a0b1-2c3d4e5f6a7b"` |
| `id_usuario` | string, identificador interno del usuario que originó la solicitud (`null` en llamadas disparadas por temporizador) | Sí | `"usr_00412"` |

`endpoint` se registra siempre como ruta normalizada (por ejemplo `/emergencias/{id}/ofertas`), sin
incluir parámetros de query ni valores sustituidos, de modo que sirva para agrupar y contar
llamadas por endpoint sin filtrar datos del dominio.

Ejemplo de un evento de log completo, exitoso:

```json
{"timestamp": "2026-10-05T18:04:09.112Z", "nivel": "INFO", "evento": "llamada_saliente", "componente_destino": "bonita", "metodo": "POST", "endpoint": "/API/bpm/process/{id}/instantiation", "codigo_estado": 200, "duracion_ms": 340, "intento": 1, "resultado": "exito", "id_correlacion": "8f3a1c22-5d6e-4f19-a0b1-2c3d4e5f6a7b", "id_usuario": "usr_00412"}
```

## 3. Datos que nunca se registran

Ningún log, de ningún nivel, puede contener:

- El encabezado `Authorization` completo.
- Tokens JWT, tokens de sesión de Bonita o el valor de `BONITA_CALLBACK_TOKEN`.
- Contraseñas, en texto plano o hasheadas.
- Cookies de sesión.
- DNI o CUIT de personas o de ONGs.
- Nombres y apellidos de personas.
- Correos electrónicos.
- Números de teléfono.
- Direcciones postales.

### Política de redacción

El cliente HTTP común de `core/integraciones/` aplica redacción automática antes de loguear
cualquier encabezado o cuerpo de solicitud o respuesta:

- Los encabezados `Authorization`, `Cookie` y `Set-Cookie` se reemplazan enteros por `"***"`; no
  se loguea ni siquiera un prefijo del valor.
- Cualquier campo del cuerpo cuyo nombre coincida con una lista de campos sensibles (`password`,
  `contrasena`, `dni`, `cuit`, `nombre`, `apellido`, `email`, `correo`, `telefono`, `direccion`,
  entre otros equivalentes del dominio) se reemplaza por `"***"` antes de que el log se emita,
  tanto si el campo está en el nivel superior del JSON como si está anidado.
- El cuerpo completo de la solicitud o la respuesta **no** se loguea por defecto; solo se loguean
  los campos definidos en la tabla de la sección 2. Si en algún momento se necesita loguear un
  fragmento del cuerpo para depurar un caso puntual, ese fragmento pasa primero por la misma
  redacción.

## 4. Identificador de correlación

Cada solicitud que entra a la aplicación web queda asociada a un `id_correlacion` (UUID) que la
acompaña en todo su recorrido:

- Se lee del encabezado `X-Correlation-Id` de la solicitud entrante.
- Si la solicitud entrante no trae ese encabezado, la aplicación web genera un UUID nuevo al
  comienzo del procesamiento.
- Ese mismo valor se propaga en el encabezado `X-Correlation-Id` de toda llamada saliente que se
  origine para atender esa solicitud, tanto hacia Bonita como hacia la API Nacional.
- Aparece en todos los eventos de log generados mientras se procesa esa solicitud, incluidos los
  de las llamadas salientes de la sección 2.
- Aparece en el campo `id_correlacion` del cuerpo de todo error devuelto al cliente, según el
  envelope definido en `docs/contratos/errores.md`.

Esto permite, dado un error reportado por un usuario con su `id_correlacion`, reconstruir en los
logs de los tres componentes (aplicación web, Bonita, API Nacional) exactamente qué ocurrió en esa
operación.

## 5. Ejemplo de traza completa

El siguiente ejemplo muestra la traza de la confirmación de una selección de ofertas: la web
busca la tarea "Seleccionar ofertas" en Bonita (el primer intento agota el timeout y el reintento
responde) y la ejecuta con los compromisos y `ongsNoSeleccionadas`, todo bajo el mismo
`id_correlacion`.

```json
{"timestamp": "2026-10-06T11:46:58.001Z", "nivel": "INFO", "evento": "solicitud_entrante", "metodo": "POST", "endpoint": "/adjudicaciones/convocatoria/{convocatoria_id}", "id_correlacion": "3c4d5e6f-3333-4c5d-8e0f-1a2b3c4d5e6f", "id_usuario": "0193f4a2-7c1e-7b5d-9a3f-2e8c4b6d1a01"}
{"timestamp": "2026-10-06T11:47:08.010Z", "nivel": "WARN", "evento": "llamada_saliente", "componente_destino": "bonita", "metodo": "GET", "endpoint": "/API/bpm/humanTask", "codigo_estado": null, "duracion_ms": 10004, "intento": 1, "resultado": "error", "id_correlacion": "3c4d5e6f-3333-4c5d-8e0f-1a2b3c4d5e6f", "id_usuario": "0193f4a2-7c1e-7b5d-9a3f-2e8c4b6d1a01"}
{"timestamp": "2026-10-06T11:47:08.690Z", "nivel": "INFO", "evento": "llamada_saliente", "componente_destino": "bonita", "metodo": "GET", "endpoint": "/API/bpm/humanTask", "codigo_estado": 200, "duracion_ms": 180, "intento": 2, "resultado": "exito", "id_correlacion": "3c4d5e6f-3333-4c5d-8e0f-1a2b3c4d5e6f", "id_usuario": "0193f4a2-7c1e-7b5d-9a3f-2e8c4b6d1a01"}
{"timestamp": "2026-10-06T11:47:09.120Z", "nivel": "INFO", "evento": "llamada_saliente", "componente_destino": "bonita", "metodo": "POST", "endpoint": "/API/bpm/userTask/{id}/execution", "codigo_estado": 204, "duracion_ms": 410, "intento": 1, "resultado": "exito", "id_correlacion": "3c4d5e6f-3333-4c5d-8e0f-1a2b3c4d5e6f", "id_usuario": "0193f4a2-7c1e-7b5d-9a3f-2e8c4b6d1a01"}
{"timestamp": "2026-10-06T11:47:09.200Z", "nivel": "INFO", "evento": "solicitud_completada", "metodo": "POST", "endpoint": "/adjudicaciones/convocatoria/{convocatoria_id}", "codigo_estado": 302, "duracion_ms": 11199, "id_correlacion": "3c4d5e6f-3333-4c5d-8e0f-1a2b3c4d5e6f", "id_usuario": "0193f4a2-7c1e-7b5d-9a3f-2e8c4b6d1a01"}
```

En el segundo evento, el primer intento contra Bonita agota el timeout de lectura de 10 segundos
(`resultado: "error"`, `codigo_estado: null`); tras el backoff, el segundo intento
(`intento: 2`) responde. La ejecución de la tarea no se reintenta porque no es idempotente. Los
cinco eventos comparten el mismo `id_correlacion`. Lo que Bonita hace después (liberar en la API
a las ONG no seleccionadas) queda en los logs de Bonita y de la API, no en los de la web.

## 6. Niveles de log

| Nivel | Uso |
|---|---|
| `DEBUG` | Detalle interno útil solo en desarrollo local (por ejemplo, parámetros de armado de una consulta). Desactivado por defecto; se habilita con `LOG_LEVEL=DEBUG` |
| `INFO` | Eventos normales del ciclo de vida de una solicitud y de las llamadas salientes exitosas: `solicitud_entrante`, `solicitud_completada`, `llamada_saliente` con `resultado: "exito"` |
| `WARN` | Situaciones anómalas pero recuperables: un intento de llamada saliente que falló pero todavía tiene reintentos disponibles, una validación de negocio rechazada (4xx esperable) |
| `ERROR` | Fallas que impactan al usuario: se agotaron los reintentos ante un sistema externo (503), una excepción no contemplada (500), una respuesta externa ilegible (502) |

El nivel mínimo efectivo se configura con la variable de entorno `LOG_LEVEL` (ver
`docs/contratos/configuracion.md`). En los entornos de evaluación y en producción se espera
`LOG_LEVEL=INFO`; `DEBUG` queda reservado al desarrollo local de cada integrante.
