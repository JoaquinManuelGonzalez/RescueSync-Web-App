# Contrato de configuración

RescueSync se configura en un 100 % por variables de entorno. Este documento describe cada
variable, la política de arranque ante configuración faltante y la gestión de secretos del
proyecto. La plantilla con todas las variables, sin valores reales, vive en `.env.example` en la
raíz del repositorio.

## 1. Tabla de variables

| Variable | Obligatoria (S/N) | Valor por defecto | Descripción | Entorno |
|---|---|---|---|---|
| `APP_ENV` | N | `local` | Identifica el entorno de ejecución (`local`, `evaluacion`, `produccion`) | Todos |
| `SECRET_KEY` | S | — | Clave secreta de Flask para firmar sesión y tokens CSRF | Todos |
| `APP_PORT` | N | `5000` | Puerto en el que escucha la aplicación dentro del contenedor, y en el que Compose la publica en el host | Todos |
| `LOG_LEVEL` | N | `INFO` | Nivel mínimo de log (`DEBUG`, `INFO`, `WARN`, `ERROR`) | Todos |
| `POSTGRES_HOST` | N | `db` | Host del servicio de PostgreSQL según `docker-compose.yml` | Todos |
| `POSTGRES_PORT` | N | `5432` | Puerto de PostgreSQL dentro de la red de contenedores | Todos |
| `POSTGRES_HOST_PORT` | N | `5432` | Puerto del host en el que `docker-compose.yml` publica PostgreSQL. Se cambia cuando el 5432 del host ya está ocupado. La consume únicamente Compose: la aplicación nunca la lee | Todos |
| `POSTGRES_DB` | N | `rescuesync` | Nombre de la base de datos | Todos |
| `POSTGRES_USER` | S | — | Usuario de PostgreSQL | Todos |
| `POSTGRES_PASSWORD` | S | — | Contraseña de PostgreSQL | Todos |
| `DATABASE_URL` | S | — | Cadena de conexión completa usada por SQLAlchemy | Todos |
| `BONITA_BASE_URL` | S | — | URL base de la REST API de Bonita | Todos |
| `BONITA_USER` | S | — | Usuario técnico con el que la aplicación abre sesión en Bonita | Todos |
| `BONITA_PASSWORD` | S | — | Contraseña del usuario técnico de Bonita | Todos |
| `BONITA_PROCESO_NOMBRE` | N | `GestionDeEmergencia` | Nombre del proceso BPMN a instanciar | Todos |
| `BONITA_PROCESO_VERSION` | N | `1.0` | Versión del proceso BPMN publicado en Bonita | Todos |
| `BONITA_TIMEOUT_S` | N | `10` | Timeout de lectura, en segundos, para llamadas a Bonita | Todos |
| `BONITA_CALLBACK_TOKEN` | S | — | Token de servicio que Bonita envía al consultar el endpoint de ofertas consolidadas (integración 4) | Todos |
| `API_NACIONAL_BASE_URL` | S | — | URL base de la API Nacional | Todos (real solo a partir de la Entrega 3) |
| `API_NACIONAL_CLIENT_ID` | S | — | Client ID para la autenticación JWT contra la API Nacional | Todos (real solo a partir de la Entrega 3) |
| `API_NACIONAL_CLIENT_SECRET` | S | — | Client secret para la autenticación JWT contra la API Nacional | Todos (real solo a partir de la Entrega 3) |
| `API_NACIONAL_TIMEOUT_S` | N | `10` | Timeout de lectura, en segundos, para llamadas a la API Nacional | Todos |
| `API_NACIONAL_REINTENTOS` | N | `2` | Cantidad de reintentos ante 5xx, timeout o error de red (no cuenta el intento original) | Todos |
| `API_NACIONAL_BACKOFF_MS` | N | `500` | Base del backoff exponencial entre reintentos, en milisegundos | Todos |
| `SESION_MINUTOS_INACTIVIDAD` | N | `30` | Minutos de inactividad tras los cuales la sesión expira. Requisito no funcional de la épica de identidad; se verifica del lado del servidor | Todos |
| `LOGIN_MAX_INTENTOS` | N | `5` | Intentos de ingreso fallidos consecutivos antes de bloquear temporalmente la cuenta | Todos |
| `LOGIN_BLOQUEO_MINUTOS` | N | `15` | Duración, en minutos, del bloqueo temporal de la cuenta | Todos |
| `CONTRASENA_LONGITUD_MINIMA` | N | `10` | Longitud mínima exigida a las contraseñas al crearlas o cambiarlas | Todos |
| `SEMILLA_CONTRASENA` | N | `RescueSync.2026` | Contraseña de las cuentas de demostración que carga `flask seed`. No es un secreto de producción: el entorno sembrado es descartable | Local y evaluación |

## 2. Arranque en modo "fail fast"

La aplicación valida la presencia de todas las variables obligatorias (columna "Obligatoria = S"
de la tabla anterior) al iniciar el proceso, antes de aceptar cualquier solicitud. Si falta una
sola variable obligatoria, o está presente pero vacía, la aplicación:

1. Registra un evento de nivel `ERROR` indicando qué variable o variables faltan, sin loguear el
   valor de ninguna variable de configuración (podrían ser secretos parcialmente completados).
2. Termina el proceso con un código de salida distinto de cero, sin llegar a levantar el servidor
   HTTP.

Este comportamiento se verifica de forma reproducible: renombrar temporalmente `.env` (o eliminar
una variable obligatoria de él) y levantar la aplicación con `docker compose up` debe hacer que el
contenedor de la aplicación termine inmediatamente en lugar de quedar sirviendo solicitudes con
una configuración incompleta. La responsabilidad de esta validación recae en el módulo `core` (ver
`docs/arquitectura/componentes.md`), ejecutada una única vez durante la construcción de la
aplicación (app factory de Flask), antes de registrar los módulos de dominio.

## 3. Diferencias entre entorno local y entorno de evaluación

| Aspecto | Entorno local | Entorno de evaluación |
|---|---|---|
| `APP_ENV` | `local` | `evaluacion` |
| Origen de las variables | Archivo `.env` propio de cada integrante, nunca versionado | Archivo `.env` propio de la máquina de evaluación, cargado por quien realiza la demostración |
| Base de datos | Contenedor PostgreSQL levantado por `docker compose`, datos descartables | Mismo contenedor, con datos de la corrida de evaluación; se puede reiniciar entre corridas |
| Bonita | Instancia local del Studio/Portal instalada en la máquina del integrante | Misma instalación, corriendo en la máquina desde la que se hace la demostración |
| API Nacional | Antes de la Entrega 3: no existe, las variables `API_NACIONAL_*` se completan con valores de prueba que la aplicación no llega a usar. Desde la Entrega 3: instancia dockerizada, propia o compartida por el equipo | Misma instancia que se use para el resto del equipo en la fecha de evaluación |
| `LOG_LEVEL` | Habitualmente `DEBUG` para facilitar el desarrollo | `INFO`, igual que en producción, para no filtrar detalle interno durante la demostración |
| `SECRET_KEY` | Valor de desarrollo, puede ser fijo por comodidad mientras no se comparta el repositorio | Valor generado especialmente para la evaluación, distinto del de cada entorno local |

En ningún caso las credenciales de un entorno se reutilizan en otro: cada `.env` es local a la
máquina que lo usa y no se transmite fuera del canal de secretos definido en la sección 4.

## 4. Gestión de secretos

- **Quién los tiene.** Cada integrante mantiene su propio `.env` local, generado a partir de
  `.env.example`, con sus propias credenciales de desarrollo (usuario y contraseña de PostgreSQL
  local, usuario técnico de Bonita local). Las credenciales compartidas del equipo (por ejemplo,
  el `BONITA_CALLBACK_TOKEN` acordado para las pruebas conjuntas, o las credenciales de una
  instancia compartida de la API Nacional) las administra quien las generó y se distribuyen solo a
  quien las necesita.
- **Por qué canal se comparten.** Los secretos del equipo se comparten exclusivamente por un canal
  privado fuera del repositorio (mensaje directo o canal privado del equipo), nunca por un `issue`,
  `pull request`, commit, ni por ningún archivo dentro del repositorio. `.env.example` documenta
  qué variables existen, nunca sus valores.
- **Qué hacer si un secreto se filtra.** Si un secreto llega a subirse por error a un commit, a un
  `pull request` o a cualquier canal expuesto:
  1. Se rota el secreto de inmediato (se genera una contraseña o token nuevo y se reemplaza en el
     sistema correspondiente: PostgreSQL, Bonita o API Nacional), sin esperar a limpiar el
     historial de git.
  2. Se notifica al resto del equipo para que actualicen su `.env` local si correspondía a una
     credencial compartida.
  3. Si el secreto llegó a quedar en el historial de git, se evalúa con el equipo si corresponde
     reescribir el historial de la rama afectada; en cualquier caso, el secreto expuesto se
     considera comprometido y no se reutiliza aunque se logre eliminar del historial.

### Verificación reproducible de que los secretos no llegan al remoto

Antes de cada push, y como parte de la incorporación de un nuevo integrante al proyecto, se
verifica que `.env` esté efectivamente ignorado por git:

```bash
git check-ignore -v .env
```

Salida esperada (confirma que la línea del `.gitignore` que lo ignora es la del bloque de
Environments, y ahora también queda cubierto por el bloque de secretos agregado al final del
archivo):

```
.gitignore:151:.env	.env
```

Con un `.env` de prueba ya creado en la raíz del repositorio, se confirma además que no aparece
como archivo para agregar en el estado del repositorio:

```bash
git status --ignored
```

Salida esperada (fragmento relevante, `.env` debe aparecer bajo "Ignored files", nunca bajo
"Untracked files" ni "Changes to be committed"):

```
Ignored files:
  (use "git add -f <file>..." to include in what will be committed)
        .env
```

Si `.env` apareciera en `git status` fuera de la sección de archivos ignorados, se debe detener
cualquier `git add` o `git commit` pendiente y revisar el `.gitignore` antes de continuar.
