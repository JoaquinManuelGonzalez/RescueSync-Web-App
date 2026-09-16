# RescueSync

RescueSync es una aplicación web para la gestión de emergencias y la coordinación de ayuda
humanitaria entre organismos municipales/regionales y ONGs, desarrollada como trabajo práctico
de la materia **Desarrollo de Software en Sistemas Distribuidos**, Curso 2026.

El sistema permite dar de alta emergencias, generar lotes de necesidad y convocatorias, recibir
ofertas de ayuda de ONGs, adjudicar esas ofertas y hacer seguimiento de la ejecución y cierre,
integrándose con un motor de procesos (Bonita) y con una API Nacional externa para validar y
reservar recursos.

## Integrantes del equipo

| Apellido, Nombre | Padrón |
|---|---|
| Cellini, Lara | 16237/5 |
| Felder, León | 21182/1 |
| González, Iván | 21816/3 |
| Gonzalez, Joaquín Manuel | 21247/1 |
| Rabasa, Ulises | 23813/9 |

## Stack tecnológico

| Componente | Tecnología | Versión |
|---|---|---|
| Runtime | Python | 3.14 |
| Backend | Flask | 3.1.3 |
| ORM | SQLAlchemy | 2.0.54 |
| Integración ORM/Flask | Flask-SQLAlchemy | 3.1.1 |
| Migraciones | Alembic (vía Flask-Migrate) | 1.20.0 (Flask-Migrate 4.1.0) |
| Driver de base de datos | psycopg | 3.3.5 |
| Base de datos | PostgreSQL (dockerizada, imagen `postgres:18-trixie`) | 18 |
| Frontend | Jinja2 + Tailwind CSS | Tailwind 4.3.3 |
| Autenticación | Flask-Login | 0.6.3 |
| Linter / formateador | Ruff | 0.16.7 |
| Motor de procesos | Bonita Open Solution >= 7.9.0 (versión exacta a confirmar por el equipo) | — |

Estilo arquitectónico: **monolito modular** (ver `docs/adr/ADR-005-estilo-arquitectonico.md`).

## Mapa del repositorio

```
.
├── app/                        codigo de la aplicacion (se crea en la epica del esqueleto ejecutable)
├── docs/
│   ├── adr/                    decisiones de arquitectura (ADRs)
│   ├── arquitectura/           diagrama de componentes e integraciones
│   └── contratos/               contratos transversales: errores, logging, configuracion
├── .github/
│   ├── pull_request_template.md
│   └── CODEOWNERS
├── .env.example                 variables de entorno de referencia (sin valores reales)
├── CONTRIBUTING.md               convenciones de codigo, ramas, commits y revision de PRs
├── README.md                     este archivo
└── LICENSE
```

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

El índice completo de ADRs, con el ciclo de vida de estados y la regla de reemplazo, está en
[docs/adr/README.md](docs/adr/README.md).

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

## Variables de entorno

Se copian desde `.env.example` a un archivo `.env` local (`cp .env.example .env` o equivalente
en Windows) y se completan con valores reales. **`.env` nunca se commitea.**

### Aplicación

| Variable | Obligatoria (S/N) | Descripción |
|---|---|---|
| `APP_ENV` | N | Entorno de ejecución (`local`, `evaluacion`, etc.) |
| `SECRET_KEY` | S | Clave secreta de Flask (sesiones, CSRF) |
| `APP_PORT` | N | Puerto donde escucha la aplicación |
| `LOG_LEVEL` | N | Nivel de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Base de datos

| Variable | Obligatoria (S/N) | Descripción |
|---|---|---|
| `POSTGRES_HOST` | N | Host del servicio de PostgreSQL |
| `POSTGRES_PORT` | N | Puerto de PostgreSQL |
| `POSTGRES_DB` | N | Nombre de la base de datos |
| `POSTGRES_USER` | S | Usuario de PostgreSQL |
| `POSTGRES_PASSWORD` | S | Contraseña de PostgreSQL |
| `DATABASE_URL` | S | Cadena de conexión completa usada por SQLAlchemy |

### Bonita

| Variable | Obligatoria (S/N) | Descripción |
|---|---|---|
| `BONITA_BASE_URL` | S | URL base de la API REST de Bonita |
| `BONITA_USER` | S | Usuario técnico de Bonita |
| `BONITA_PASSWORD` | S | Contraseña del usuario técnico de Bonita |
| `BONITA_PROCESO_NOMBRE` | N | Nombre del proceso BPMN a instanciar |
| `BONITA_PROCESO_VERSION` | N | Versión del proceso BPMN |
| `BONITA_TIMEOUT_S` | N | Timeout en segundos para llamadas a Bonita |
| `BONITA_CALLBACK_TOKEN` | S | Token de servicio que Bonita usa para llamar al endpoint de ofertas consolidadas |

### API Nacional

| Variable | Obligatoria (S/N) | Descripción |
|---|---|---|
| `API_NACIONAL_BASE_URL` | S | URL base de la API Nacional |
| `API_NACIONAL_CLIENT_ID` | S | Client ID para autenticación |
| `API_NACIONAL_CLIENT_SECRET` | S | Client secret para autenticación |
| `API_NACIONAL_TIMEOUT_S` | N | Timeout en segundos para llamadas a la API Nacional |
| `API_NACIONAL_REINTENTOS` | N | Cantidad de reintentos ante error transitorio |
| `API_NACIONAL_BACKOFF_MS` | N | Backoff inicial en milisegundos entre reintentos |

Las variables marcadas `S` son obligatorias y no tienen valor por defecto: la aplicación debe
fallar al arrancar si falta alguna (ver `docs/contratos/configuracion.md`).

## Cómo levantar el sistema

> **Advertencia:** este repositorio contiene, por ahora, únicamente las decisiones de
> arquitectura y los contratos del sistema. El esqueleto ejecutable (`Dockerfile`,
> `docker-compose.yml`, `requirements.txt`, `package.json` y la app factory de Flask) se
> incorpora en la épica siguiente. Hasta entonces, los pasos de abajo describen el flujo
> previsto pero no son ejecutables en el estado actual del repositorio.

1. Clonar el repositorio y copiar `.env.example` a `.env`, completando los valores reales.
2. Levantar los contenedores (aplicación + base de datos): `docker compose up`.
3. Aplicar migraciones de base de datos: `flask db upgrade`.
4. Acceder a la aplicación en `http://localhost:<APP_PORT>`.

## Antes de tu primer commit

Leé [CONTRIBUTING.md](CONTRIBUTING.md): define el idioma del código, la nomenclatura por capa,
la estructura de carpetas, el formateo con Ruff, la nomenclatura de ramas, la revisión
obligatoria de PRs y la convención de commits ligada al backlog (HUs). Es de lectura
obligatoria antes de abrir el primer Pull Request.
