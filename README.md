# RescueSync

RescueSync es una aplicación web para la gestión de emergencias y la coordinación de ayuda
humanitaria entre organismos municipales/regionales y ONGs, desarrollada como trabajo práctico
de la materia **Desarrollo de Software en Sistemas Distribuidos**, Curso 2026.

El sistema permite dar de alta emergencias, generar lotes de necesidad y convocatorias, recibir
ofertas de ayuda de ONGs, adjudicar esas ofertas y hacer seguimiento de la ejecución y cierre,
integrándose con un motor de procesos (Bonita) y con una API Nacional externa para validar y
reservar recursos.

---

## Puesta en marcha

### Requisitos previos

Hay que instalar dos herramientas: **Docker** y **uv**. La aplicación, la base de datos y la
cadena de build del frontend corren siempre en contenedores: **no se instala Python, ni Node,
ni PostgreSQL en la máquina**.

uv es el gestor de dependencias del backend ([ADR-008](docs/adr/ADR-008-gestion-dependencias-uv.md)).
Se instala en el host porque es el que arma el entorno local que usan el editor, Ruff y pytest
fuera del contenedor, y el que regenera `backend/uv.lock` al agregar una dependencia. El
intérprete de Python 3.14 lo descarga y administra el propio uv: no hay que instalar Python
aparte.

| Requisito | Versión mínima | Cómo verificar |
|---|---|---|
| Docker Engine | 25.0 | `docker --version` |
| Docker Compose | v2.24 (plugin `docker compose`, no `docker-compose`) | `docker compose version` |
| uv | 0.12.13 (la misma que fija `backend/Dockerfile`) | `uv --version` |
| Git | 2.40 | `git --version` |

En **Windows** hace falta Docker Desktop con el backend **WSL 2** activado (Settings → General →
*Use the WSL 2 based engine*). En **macOS** y **Linux**, Docker Desktop o Docker Engine con el
plugin de Compose.

#### Instalar uv

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/0.12.13/install.ps1 | iex"
```

macOS / Linux:

```bash
curl -LsSf https://astral.sh/uv/0.12.13/install.sh | sh
```

Alternativas equivalentes: `winget install --id=astral-sh.uv -e` en Windows, `brew install uv`
en macOS, `pipx install uv==0.12.13` en cualquier sistema.

El instalador agrega uv al `PATH`: hay que **abrir una terminal nueva** antes de verificarlo.

```bash
uv --version
```

Tiene que responder `uv 0.12.13`.

> Instalá la **0.12.13**, que es la versión que usa la imagen de Docker (argumento `UV_VERSION`
> en `backend/Dockerfile`). Una versión más nueva funciona, pero puede reescribir
> `backend/uv.lock` con un formato distinto y ensuciar los diffs del equipo. Para actualizar
> uv más adelante: `uv self update`.

### Pasos

**1. Clonar el repositorio**

```bash
git clone https://github.com/JoaquinManuelGonzalez/RescueSync-Web-App.git
cd RescueSync-Web-App
```

**2. Preparar el entorno local de Python con uv**

```bash
cd backend
uv sync --locked
cd ..
```

`uv sync` lee `pyproject.toml` y `uv.lock`, descarga el intérprete Python 3.14 que fija
`.python-version` si todavía no lo tenés, y crea `backend/.venv` con exactamente las mismas
versiones que se instalan dentro de la imagen, incluidas las de desarrollo (Ruff y pytest).
La bandera `--locked` hace que el comando falle si el lock quedó desincronizado de
`pyproject.toml`, en vez de regenerarlo por su cuenta.

Esto **no reemplaza a Docker**: la aplicación sigue corriendo en contenedores. El entorno local
existe para que el editor resuelva los imports y el autocompletado, y para poder correr
`uv run ruff` y `uv run pytest` sin levantar el entorno completo.

`backend/.venv` está en `.gitignore`: no se commitea nunca.

> Si falla diciendo que el lock está desactualizado, ver
> [Problemas conocidos](#problemas-conocidos), punto 8.

**3. Crear el archivo `.env` a partir de la plantilla**

Linux / macOS / Git Bash:

```bash
cp .env.example .env
```

Windows (PowerShell):

```powershell
Copy-Item .env.example .env
```

**4. Completar las variables obligatorias del `.env`**

Abrir `.env` y completar las marcadas con `(*)`. Son las de la tabla de más abajo que dicen
`Sí` en la columna *Obligatoria*. Para desarrollo local alcanza con valores inventados, salvo
que quieras integrarte con Bonita de verdad. Un ejemplo funcional:

```
SECRET_KEY=una-clave-larga-y-aleatoria-distinta-por-entorno
POSTGRES_USER=rescuesync
POSTGRES_PASSWORD=rescuesync_local
DATABASE_URL=postgresql+psycopg://rescuesync:rescuesync_local@db:5432/rescuesync
BONITA_BASE_URL=http://host.docker.internal:8080/bonita
BONITA_USER=install
BONITA_PASSWORD=install
BONITA_CALLBACK_TOKEN=un-token-compartido-del-equipo
API_NACIONAL_BASE_URL=http://api-nacional.invalido
API_NACIONAL_CLIENT_ID=pendiente-entrega-3
API_NACIONAL_CLIENT_SECRET=pendiente-entrega-3
```

> `DATABASE_URL` tiene que ser consistente con `POSTGRES_USER`, `POSTGRES_PASSWORD` y
> `POSTGRES_DB`, y apuntar al host `db` (el nombre del servicio en la red de contenedores),
> nunca a `localhost`.
>
> Las variables `API_NACIONAL_*` no se usan hasta la Entrega 3, pero son obligatorias: la
> aplicación no arranca sin ellas. Cualquier valor de relleno sirve por ahora.

**5. Construir las imágenes** (solo la primera vez, o cuando cambien las dependencias)

```bash
docker compose build
```

**6. Levantar el entorno**

```bash
docker compose up -d
```

**7. Verificar que responde**

```bash
curl http://localhost:5000/health
```

Respuesta esperada:

```json
{"status": "ok", "db": "ok"}
```

En PowerShell, `curl` es un alias de `Invoke-WebRequest`; usar `curl.exe http://localhost:5000/health`
o abrir esa URL en el navegador.

**8. Abrir la aplicación en el navegador**

<http://localhost:5000>

Vas a ver la página de estado del entorno: si se ve **con estilos**, la cadena completa
funciona (Flask sirve, encuentra las plantillas de `frontend/` y Tailwind compiló el CSS). La
página informa el estado de la base, la revisión del esquema aplicada y qué módulos de dominio
están registrados y cuáles siguen pendientes.

> Es una página de diagnóstico, no una pantalla de producto. Cuando exista el módulo
> `usuarios_roles`, la ruta `/` pasa a ser el login o el panel según la sesión.

Eso es todo. El contenedor `web` aplica las migraciones pendientes solo, antes de levantar el
servidor, y el contenedor `tailwind` compila el CSS y se queda vigilando cambios.

**9. Cargar los datos de prueba**

```bash
docker compose exec web flask seed
```

Carga las organizaciones de demostración, el catálogo de permisos, los cinco roles con sus
permisos y una cuenta por perfil. Es idempotente: se puede volver a correr las veces que haga
falta. Al terminar imprime los emails disponibles; las contraseñas están en
[Credenciales de prueba](#credenciales-de-prueba).

---

## Stack tecnológico

| Componente | Tecnología | Versión |
|---|---|---|
| Runtime | Python | 3.14 |
| Gestor de dependencias | uv | 0.12.13 |
| Backend | Flask | 3.1.3 |
| ORM | SQLAlchemy | 2.0.54 |
| Integración ORM/Flask | Flask-SQLAlchemy | 3.1.1 |
| Migraciones | Alembic (vía Flask-Migrate) | 1.20.0 (Flask-Migrate 4.1.0) |
| Driver de base de datos | psycopg | 3.3.5 |
| Base de datos | PostgreSQL (dockerizada, imagen `postgres:18-trixie`) | 18 |
| Frontend | Jinja2 + Tailwind CSS | Tailwind 4.3.3 |
| Cadena de build del frontend | Node.js (dockerizado, imagen `node:22-alpine`) | 22 LTS |
| Autenticación | Flask-Login | 0.6.3 |
| Formularios | Flask-WTF / WTForms | 1.3.0 / 3.2.2 |
| Servidor de producción | gunicorn | 26.2.0 |
| Carga de `.env` | python-dotenv | 1.2.3 |
| Linter / formateador | Ruff | 0.16.7 |
| Tests | pytest | 9.1.1 |
| Motor de procesos | Bonita Open Solution >= 7.9.0 (versión exacta a confirmar por el equipo) | — |

Estilo arquitectónico: **monolito modular** (ver `docs/adr/ADR-005-estilo-arquitectonico.md`).

---

## Mapa del repositorio

```
.
├── backend/                     codigo Python de la aplicacion
│   ├── app/
│   │   ├── core/                 configuracion, errores, logging, seguridad, integraciones
│   │   └── modulos/              un paquete por modulo de dominio
│   ├── migrations/               migraciones de Alembic
│   ├── tests/
│   ├── pyproject.toml            dependencias (uv) y configuracion de Ruff
│   ├── uv.lock
│   └── Dockerfile
├── frontend/                    plantillas Jinja, estaticos y cadena de build de Tailwind
│   ├── plantillas/
│   ├── estaticos/
│   ├── src/input.css
│   ├── observar.sh               bucle que recompila el CSS al cambiar una plantilla
│   ├── package.json
│   └── Dockerfile
├── docs/
│   ├── adr/                     decisiones de arquitectura (ADRs)
│   ├── arquitectura/            diagrama de componentes e integraciones
│   └── contratos/                contratos transversales: errores, logging, configuracion, autorizacion
├── .github/
├── docker-compose.yml           db + web + tailwind
├── .env.example                 variables de entorno de referencia (sin valores reales)
├── .python-version              version del interprete que uv instala y usa en el host
├── CONTRIBUTING.md               convenciones de codigo, ramas, commits y revision de PRs
└── README.md                     este archivo
```

---

## Variables de entorno

Se copian desde `.env.example` a un archivo `.env` local y se completan con valores reales.
**`.env` nunca se commitea.** La tabla completa, con la política de fail-fast y la gestión de
secretos, está en [`docs/contratos/configuracion.md`](docs/contratos/configuracion.md).

| Variable | Obligatoria | Valor de ejemplo | Descripción |
|---|---|---|---|
| `APP_ENV` | No | `local` | Entorno de ejecución (`local`, `evaluacion`, `produccion`) |
| `SECRET_KEY` | **Sí** | `k3yAleatoria...` | Clave secreta de Flask (sesiones, CSRF). Distinta por entorno |
| `APP_PORT` | No | `5000` | Puerto de la aplicación, dentro del contenedor y publicado en el host |
| `LOG_LEVEL` | No | `INFO` | Nivel mínimo de log (`DEBUG`, `INFO`, `WARN`, `ERROR`) |
| `POSTGRES_HOST` | No | `db` | Host de PostgreSQL. Es el nombre del servicio, no `localhost` |
| `POSTGRES_PORT` | No | `5432` | Puerto de PostgreSQL dentro de la red de contenedores |
| `POSTGRES_HOST_PORT` | No | `5432` | Puerto del **host** donde se publica PostgreSQL. Cambiarlo si el 5432 ya está ocupado |
| `POSTGRES_DB` | No | `rescuesync` | Nombre de la base de datos |
| `POSTGRES_USER` | **Sí** | `rescuesync` | Usuario de PostgreSQL |
| `POSTGRES_PASSWORD` | **Sí** | `rescuesync_local` | Contraseña de PostgreSQL |
| `DATABASE_URL` | **Sí** | `postgresql+psycopg://rescuesync:rescuesync_local@db:5432/rescuesync` | Cadena de conexión de SQLAlchemy |
| `BONITA_BASE_URL` | **Sí** | `http://host.docker.internal:8080/bonita` | URL base de la API REST de Bonita |
| `BONITA_USER` | **Sí** | `install` | Usuario técnico de Bonita |
| `BONITA_PASSWORD` | **Sí** | `install` | Contraseña del usuario técnico de Bonita |
| `BONITA_PROCESO_NOMBRE` | No | `GestionDeEmergencia` | Nombre del proceso BPMN a instanciar |
| `BONITA_PROCESO_VERSION` | No | `1.0` | Versión del proceso BPMN publicado |
| `BONITA_TIMEOUT_S` | No | `10` | Timeout de lectura, en segundos, hacia Bonita |
| `BONITA_CALLBACK_TOKEN` | **Sí** | `token-compartido` | Token con el que Bonita se autentica al pedir las ofertas consolidadas |
| `API_NACIONAL_BASE_URL` | **Sí** | `http://api-nacional.invalido` | URL base de la API Nacional (real desde la Entrega 3) |
| `API_NACIONAL_CLIENT_ID` | **Sí** | `pendiente-entrega-3` | Client ID para la autenticación JWT |
| `API_NACIONAL_CLIENT_SECRET` | **Sí** | `pendiente-entrega-3` | Client secret para la autenticación JWT |
| `API_NACIONAL_TIMEOUT_S` | No | `10` | Timeout de lectura, en segundos, hacia la API Nacional |
| `API_NACIONAL_REINTENTOS` | No | `2` | Reintentos ante error transitorio (sin contar el intento original) |
| `API_NACIONAL_BACKOFF_MS` | No | `500` | Backoff inicial entre reintentos, en milisegundos |

Si falta una variable obligatoria, **el contenedor `web` termina con código distinto de cero** y
el log indica exactamente cuál falta. No se aplica ningún valor por defecto.

---

## Credenciales de prueba

Las que deja `docker compose exec web flask seed`. Todas comparten la contraseña de
`SEMILLA_CONTRASENA` (por defecto `RescueSync.2026`).

| Rol | Email | Organización |
|---|---|---|
| Operador Municipal | `operador@chascomus.test` | Municipio de Chascomús |
| Centro Coordinador Regional | `coordinador@rescuesync.test` | Centro Coordinador Regional Buenos Aires |
| Representante de ONG | `representante@cruzsolidaria.test` | Cruz Solidaria |
| Representante de ONG | `representante@manosunidas.test` | Manos Unidas |
| Auditor / Directivo | `auditor@rescuesync.test` | — |
| Administrador | `admin@rescuesync.test` | — |

Las contraseñas se almacenan hasheadas con scrypt (`backend/app/core/seguridad.py`), nunca en
texto plano.

En RescueSync **no hay autorregistro**: todas las cuentas las crea el administrador desde
`/usuarios`. La primera cuenta de administrador de un entorno nuevo no puede salir de ahí
—el panel exige estar autenticado como administrador—, así que se crea por consola:

```bash
docker compose exec web flask crear-administrador \
  --email admin@tu-dominio.test --nombre "Nombre y apellido"
```

Si se omite `--contrasena`, el comando genera una y la imprime **una sola vez**.

Las cuentas creadas desde el panel nacen obligadas a cambiar la contraseña en el primer
ingreso: la clave inicial la eligió otra persona y viajó por un canal externo al sistema.
El detalle completo está en [docs/contratos/autorizacion.md](docs/contratos/autorizacion.md).

---

## Comandos frecuentes

Todos se corren desde la raíz del repositorio.

| Qué necesito | Comando |
|---|---|
| Levantar el entorno | `docker compose up -d` |
| Bajarlo (conservando los datos) | `docker compose down` |
| Bajarlo y **borrar la base** | `docker compose down -v` |
| Ver el estado de los servicios | `docker compose ps` |
| Ver los logs de la aplicación | `docker compose logs -f web` |
| Ver los logs de Tailwind | `docker compose logs -f tailwind` |
| Abrir una shell en el contenedor | `docker compose exec web bash` |
| Abrir `psql` contra la base | `docker compose exec db sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB'` |
| Crear una migración nueva | `docker compose exec web flask db migrate -m "descripcion del cambio"` |
| Aplicar migraciones a mano | `docker compose exec web flask db upgrade` |
| Ver la revisión actual | `docker compose exec web flask db current` |
| Cargar datos semilla | `docker compose exec web flask seed` |
| Crear la primera cuenta de administrador | `docker compose exec web flask crear-administrador --email <email> --nombre "<nombre>"` |
| Correr los tests | `docker compose exec web pytest` |
| Formatear el código | `docker compose exec web ruff format .` |
| Verificar formato y lint | `docker compose exec web ruff format --check . && docker compose exec web ruff check .` |
| Reconstruir tras cambiar dependencias | `docker compose build web && docker compose up -d web` |
| Reinicio limpio y completo | `docker compose down -v && docker compose up -d` |

### Trabajar con uv

Estos se corren desde `backend/`, en el host (no dentro del contenedor).

| Qué necesito | Comando |
|---|---|
| Crear o actualizar el entorno local | `uv sync --locked` |
| Verificar que el lock está sincronizado con `pyproject.toml` | `uv lock --check` |
| Agregar una dependencia de la aplicación | `uv add "paquete==1.2.3"` |
| Agregar una dependencia solo de desarrollo | `uv add --dev "paquete==1.2.3"` |
| Quitar una dependencia | `uv remove paquete` |
| Regenerar el lock después de editar `pyproject.toml` a mano | `uv lock` |
| Ver el árbol de dependencias | `uv tree` |
| Formatear el código sin levantar Docker | `uv run ruff format .` |
| Verificar formato y lint sin levantar Docker | `uv run ruff format --check . && uv run ruff check .` |
| Correr los tests sin levantar Docker | `uv run pytest` |
| Actualizar el propio uv | `uv self update` |

**Agregar una dependencia de Python**, de punta a punta:

```bash
cd backend
uv add "requests==2.32.5"          # actualiza pyproject.toml y uv.lock
cd ..
docker compose build web && docker compose up -d web
```

Reglas que fijan el [ADR-002](docs/adr/ADR-002-framework-backend.md) y el
[ADR-008](docs/adr/ADR-008-gestion-dependencias-uv.md):

- Siempre con versión exacta (`==`), nunca con un rango.
- Lo que solo sirve para desarrollar (linters, tests) va con `--dev`, para que no entre en la
  imagen de producción.
- `backend/uv.lock` se commitea **siempre** junto al `pyproject.toml`, en el mismo commit: la
  imagen se construye con `uv sync --locked` y falla si el lock quedó viejo.
- `uv.lock` no se edita a mano jamás; si hay conflicto, se regenera.
- La dependencia nueva se suma además a la tabla de [Stack tecnológico](#stack-tecnológico), en
  el mismo PR.

> Ruff y pytest se pueden correr con `uv run` en el host o con `docker compose exec web`
> adentro del contenedor: es lo mismo, las dos rutas instalan el mismo `uv.lock`. Con `uv run`
> arrancan más rápido; adentro del contenedor tenés la base de datos a mano.

---

## Problemas conocidos

**1. `Error: port is already allocated` o `bind: address already in use` en el 5432**

Ya tenés otro PostgreSQL corriendo en la máquina. No hay que apagarlo: agregá al `.env`

```
POSTGRES_HOST_PORT=5433
```

y volvé a levantar. La aplicación se conecta por la red interna de contenedores, así que sigue
funcionando sin tocar ningún archivo versionado. Si el que está ocupado es el 5000, lo mismo
con `APP_PORT`.

**2. `exec /usr/local/bin/entrypoint.sh: no such file or directory` (Windows)**

El script se clonó con finales de línea CRLF. El repositorio trae un `.gitattributes` que lo
previene, pero si clonaste antes de que existiera:

```bash
git config core.autocrlf false
git rm --cached -r .
git reset --hard
docker compose build web
```

**3. Guardo un `.py` y el cambio no se ve**

La recarga en caliente está activa y funciona sobre el bind mount. Si aun así no dispara:

- Verificá que estés editando dentro de `backend/`, no dentro de la imagen.
- Mirá `docker compose logs -f web`: si el proceso murió por un error de sintaxis, no hay
  reloader que valga. Corregí el error y se reinicia solo.
- Si cambiaste `pyproject.toml`, eso **sí** requiere `docker compose build web`.

**4. El contenedor `web` arranca y se muere enseguida**

Casi siempre es una variable obligatoria faltante o una migración que falló. Mirá el log:

```bash
docker compose logs web
```

- `Falta la variable de entorno obligatoria: X` → completá `X` en tu `.env`.
- Un error de Alembic → el log indica la revisión que falló (`Running upgrade 0001 -> 0002_...`).
  Corregí esa migración; si la base local es descartable, `docker compose down -v && docker compose up -d`.

Después de arreglarlo, `docker compose up -d web` lo vuelve a levantar.

El servicio `web` está configurado con `restart: "no"` a propósito: si la configuración está
mal, tiene que quedar muerto y visible, no reiniciándose en bucle.

**5. La página se ve sin estilos, o las clases nuevas no se aplican**

El CSS lo genera el contenedor `tailwind` en `frontend/estaticos/css/app.css`. Primero mirá si
está vivo y qué dice:

```bash
docker compose logs tailwind
```

Tiene que decir `[tailwind] vigilando ./src y ./plantillas cada 2s`. Si no aparece, o el
contenedor está reiniciándose, `docker compose restart tailwind`.

Después de guardar una plantilla, la recompilación tarda hasta 2 segundos; recargá el navegador
con Ctrl+F5 para saltear la caché. Si querés que reaccione más rápido, agregá
`INTERVALO_WATCH_S=1` al `.env`.

> **Por qué hay un bucle propio y no `tailwindcss --watch`:** ese modo se apoya en inotify, y
> los eventos del sistema de archivos no atraviesan un bind mount de Windows ni de macOS. El
> proceso queda vivo pero sordo: compila una vez al arrancar y nunca más, sin dar ningún
> síntoma. `frontend/observar.sh` compara marcas de tiempo, que funciona igual en los tres
> sistemas operativos. La variable `CHOKIDAR_USEPOLLING` **no** sirve acá: Tailwind 4 no usa
> chokidar.

**6. El contenedor `db` no arranca y el log habla de `/var/lib/postgresql/data`**

Tenés un volumen creado con la convención anterior a PostgreSQL 18. Como los datos locales son
descartables:

```bash
docker compose down -v && docker compose up -d
```

**7. Docker Desktop sin WSL 2 (Windows)**

Si los contenedores arrancan muy lento o los bind mounts se comportan raro, verificá en
Docker Desktop → Settings → General que esté tildado *Use the WSL 2 based engine*. Con el
backend Hyper-V el rendimiento del bind mount es notablemente peor.

**8. `uv sync --locked` o `docker compose build` fallan porque el lock está desactualizado**

Alguien modificó `backend/pyproject.toml` sin regenerar `backend/uv.lock`. Es exactamente lo
que `--locked` existe para detectar. Se regenera y se reconstruye:

```bash
cd backend
uv lock
cd ..
docker compose build web
```

El `uv.lock` regenerado se commitea junto al `pyproject.toml` que lo causó.

**9. Conflicto de merge en `backend/uv.lock`**

`uv.lock` es un archivo generado: **no se resuelve a mano**. Se toma cualquiera de las dos
versiones en conflicto y se regenera a partir del `pyproject.toml` ya mergeado:

```bash
git checkout origin/main -- backend/uv.lock
cd backend
uv lock
cd ..
git add backend/uv.lock
```

**10. `uv: command not found` / `uv no se reconoce como un comando interno o externo`**

El instalador agregó uv al `PATH`, pero la terminal que ya tenías abierta conserva el `PATH`
viejo: cerrala y abrí una nueva. Si aun así no aparece, verificá que `~/.local/bin`
(Linux/macOS) o `%USERPROFILE%\.local\bin` (Windows) esté en el `PATH`.

---

## Bonita

Bonita **no** forma parte del `docker-compose.yml`: es un componente externo con su propio
ciclo de vida, y así lo fijaron el
[ADR-004](docs/adr/ADR-004-motor-base-de-datos.md) y el
[ADR-005](docs/adr/ADR-005-estilo-arquitectonico.md). La aplicación se integra con él
únicamente por HTTP.

### Instalación

1. Descargar **Bonita Community** (Studio, que incluye el runtime) desde
   [bonitasoft.com](https://www.bonitasoft.com/downloads). La versión mínima acordada es
   **7.9.0**; el equipo tiene que confirmar y fijar la versión exacta que usará en la entrega,
   y todos instalar la misma.
2. Bonita Studio necesita una JDK. El instalador la incluye en la mayoría de las
   distribuciones; si no, instalar la que indique la documentación de la versión elegida.
3. Descomprimir e iniciar el Studio. La primera vez tarda varios minutos en levantar el
   runtime embebido.
4. El portal queda en `http://localhost:8080/bonita`. Las credenciales por defecto del entorno
   de desarrollo son `install` / `install`.

### Conectarlo con la aplicación

El contenedor `web` no ve el `localhost` de tu máquina: tiene el suyo. Para alcanzar un Bonita
que corre en el host, en el `.env`:

```
BONITA_BASE_URL=http://host.docker.internal:8080/bonita
```

En Windows y macOS `host.docker.internal` funciona sin configuración extra. En **Linux**, hay
que agregar al servicio `web` del `docker-compose.yml`:

```yaml
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

Para verificar la conectividad desde el contenedor:

```bash
docker compose exec web python -c "import urllib.request,os; print(urllib.request.urlopen(os.environ['BONITA_BASE_URL'], timeout=5).status)"
```

> Bonita consume del orden de 2 a 4 GB de RAM. No hace falta tenerlo levantado para trabajar
> en la aplicación web: solo para las historias que integran con el motor de procesos.

---

## Registro de validaciones de la puesta en marcha

Cada integrante que sigue este README desde cero en una carpeta limpia anota acá el resultado.
Lo que falle se corrige en el README antes de cerrar la HU.

| Integrante | Sistema operativo | Fecha | Tiempo hasta `/health` en 200 | Incidencias |
|---|---|---|---|---|
| Redactor del README, en carpeta limpia | Windows 11, Docker Desktop 29.7.2 (WSL 2) | 2026-09-18 | 14 s desde `cp .env.example .env` (imágenes ya construidas) | Ninguna. Los pasos funcionaron sin corrección |
| _(pendiente: validación por un integrante distinto del que redactó el README — CA-03)_ | | | | |

---

## Documentación del proyecto

### Registro de decisiones de arquitectura (ADR)

| ADR | Título | Estado | Enlace |
|---|---|---|---|
| ADR-001 | Framework de frontend (Jinja2 + Tailwind CSS) | Aceptado | [docs/adr/ADR-001-framework-frontend.md](docs/adr/ADR-001-framework-frontend.md) |
| ADR-002 | Framework de backend (Python + Flask) | Aceptado | [docs/adr/ADR-002-framework-backend.md](docs/adr/ADR-002-framework-backend.md) |
| ADR-003 | ORM (SQLAlchemy) | Aceptado | [docs/adr/ADR-003-orm.md](docs/adr/ADR-003-orm.md) |
| ADR-004 | Motor de base de datos (PostgreSQL dockerizada) | Aceptado | [docs/adr/ADR-004-motor-base-de-datos.md](docs/adr/ADR-004-motor-base-de-datos.md) |
| ADR-005 | Estilo arquitectónico (monolito modular) | Aceptado | [docs/adr/ADR-005-estilo-arquitectonico.md](docs/adr/ADR-005-estilo-arquitectonico.md) |
| ADR-006 | Contrato de errores, logs y configuración | Aceptado | [docs/adr/ADR-006-contrato-errores-logs-configuracion.md](docs/adr/ADR-006-contrato-errores-logs-configuracion.md) |
| ADR-007 | Estructura del esqueleto ejecutable y cadena de build de frontend | Propuesto | [docs/adr/ADR-007-estructura-esqueleto-ejecutable.md](docs/adr/ADR-007-estructura-esqueleto-ejecutable.md) |
| ADR-008 | Gestión de dependencias de Python con uv | Propuesto | [docs/adr/ADR-008-gestion-dependencias-uv.md](docs/adr/ADR-008-gestion-dependencias-uv.md) |
| ADR-009 | Autenticación por sesión y control de accesos basado en roles | Propuesto | [docs/adr/ADR-009-autenticacion-y-rbac.md](docs/adr/ADR-009-autenticacion-y-rbac.md) |

El índice completo de ADRs, con el ciclo de vida de estados, la regla de reemplazo y la de
enmienda parcial, está en [docs/adr/README.md](docs/adr/README.md).

### Arquitectura

[docs/arquitectura/componentes.md](docs/arquitectura/componentes.md) — diagrama de los 5
componentes del sistema, tabla de integraciones y módulos internos de la aplicación web con su
regla de dependencia.

### Contratos transversales

| Contrato | Contenido | Enlace |
|---|---|---|
| Errores | Envelope único de error y política de reintentos hacia sistemas externos | [docs/contratos/errores.md](docs/contratos/errores.md) |
| Logging | Formato de logs, campos obligatorios y datos que nunca se registran | [docs/contratos/logging.md](docs/contratos/logging.md) |
| Configuración | Variables de entorno, fail-fast y gestión de secretos | [docs/contratos/configuracion.md](docs/contratos/configuracion.md) |
| Autorización | Perfiles, catálogo de permisos, cómo se protege una pantalla, sesión y respuesta ante acceso no autorizado | [docs/contratos/autorizacion.md](docs/contratos/autorizacion.md) |

---

## Antes de tu primer commit

Leé [CONTRIBUTING.md](CONTRIBUTING.md): define el idioma del código, la nomenclatura por capa,
la estructura de carpetas, el formateo con Ruff, la nomenclatura de ramas, la revisión
obligatoria de PRs y la convención de commits ligada al backlog (HUs). Es de lectura
obligatoria antes de abrir el primer Pull Request.
