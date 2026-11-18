# ADR-011: Claves UUID en todas las entidades

- Estado: Propuesto
- Fecha: 2026-11-17
- Reemplaza a: —
- Reemplazado por: —

## Contexto

Todas las tablas usaban claves enteras autoincrementales (ADR-003 no fijaba el tipo de las
claves). Cada integrante corre su propia aplicación web con su propia base, y todas usan la
**misma** API del Sistema Nacional, desplegada en Render. Bonita le pasa a esa API el id de la
emergencia de la web, y la API lo usa como clave de los compromisos de recursos.

Como cada base numera desde 1, la emergencia `1` de un integrante y la `1` de otro eran, para la
API, la misma emergencia:

- la segunda evaluación chocaba con los compromisos de la primera (409) y trababa el proceso;
- liberar o finalizar la emergencia de un integrante devolvía el stock comprometido por otro;
- una emergencia finalizada por alguien dejaba esa numeración inutilizable para todos.

Limpiar la base de la API antes de cada prueba solo esconde el problema, y no sirve cuando varias
personas prueban a la vez.

## Decisión

Todas las claves primarias y foráneas de la aplicación web son UUID (`Uuid` de SQLAlchemy, tipo
`uuid` de PostgreSQL). La API del Sistema Nacional hizo el mismo cambio (su ADR-006), y exige un
UUID para identificar una emergencia.

- **Generación:** UUIDv7 con `nuevo_id()` de `backend/app/core/identificadores.py`
  (`uuid.uuid7()` de Python 3.14). Lleva la hora al principio: ordenar por `id` sigue siendo
  ordenar por fecha de alta, y el índice crece al final como con un entero.
- **Lectura:** los ids que llegan como texto (formularios, JSON, Bonita) se leen con
  `parsear_id()` / `exigir_id()`, que aceptan el UUID con o sin guiones y en mayúsculas, y
  rechazan un entero. Los formularios usan `CampoId`; las rutas, `<uuid:...>`.
- **Integración:** todos los ids viajan como texto, en el JSON de las ofertas consolidadas, en
  `POST /ofertas/evaluaciones` y en las variables del proceso (`emergenciaIdInput`,
  `convocatoriaIdInput`, `adjudicacionIdInput`). Ningún script de Bonita los convierte a número.
- **En pantalla:** el filtro `id_corto` muestra una referencia corta cuando hace falta un id
  visible.
- **Migración sin pérdida de datos** (`9e4b7c1d2a53`): convierte cada clave y sus foráneas,
  rehace las restricciones con el mismo nombre, traduce los ids guardados como texto
  (`notificacion.enlace` y `oferta_version.items_snapshot`) y tiene downgrade. Se probó en los
  dos sentidos con una copia de una base local con datos.

### Versión fijada

| Tecnología | Versión | Archivo del repositorio donde se fija |
|---|---|---|
| Python (`uuid.uuid7`) | 3.14 | `.python-version`, `backend/pyproject.toml`, `backend/Dockerfile` |
| SQLAlchemy (`Uuid`) | 2.0.54 | `backend/pyproject.toml` |

### Alternativas consideradas

| Alternativa | A favor | En contra | Motivo del descarte |
|---|---|---|---|
| Limpiar la base de la API antes de evaluar | Sin cambios de código | No evita el choque entre integrantes que prueban a la vez | Mitiga, no resuelve |
| Prefijar el id de la emergencia con el entorno | Cambio chico | Depende de que cada web se configure bien | Frágil |
| UUID solo en `emergencia`, enteros en el resto | Migración más chica | Dos criterios de clave en el mismo esquema; cualquier otro id que viaje (convocatoria, oferta) tendría el mismo problema | Incompleto |
| UUIDv4 | Estándar | Inserciones al azar en el índice; ordenar por id deja de ser orden de alta | UUIDv7 resuelve las dos cosas |

## Consecuencias

### Positivas

- Varias webs pueden usar la misma API a la vez sin pisarse los compromisos.
- Un id ya no revela cuántas emergencias, ofertas o usuarios hay, ni se puede adivinar el
  siguiente.
- `order_by(id)` conserva su significado: ninguna consulta tuvo que cambiar de orden.

### Negativas

- **Cambio incompatible:** el proceso de Bonita y la API se actualizan junto con la web. Un
  `.proc` que todavía haga `Integer.parseInt(convocatoriaId)` recibe 400 de
  `POST /ofertas/evaluaciones`.
- Al migrar se cierran las sesiones abiertas (la cookie guarda el id viejo): hay que volver a
  iniciar sesión.
- Las URLs son más largas, y un enlace guardado con un id entero deja de funcionar (los de las
  notificaciones se traducen en la migración).

### Qué nos obliga a hacer

- Toda tabla nueva usa `Uuid` con `default=nuevo_id`; las rutas con ids, `<uuid:...>`; los
  formularios, `CampoId`; los ids que llegan como texto, `parsear_id()`.
- Un id que se guarda dentro de un texto (un enlace, un JSON) se escribe con `str(uuid)`, y una
  migración que cambie claves tiene que traducirlo.
- Un cambio de este tipo se coordina con el repositorio de la API y con el proceso de Bonita, y
  se mergea el mismo día.
