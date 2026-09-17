# ADR-003: ORM y migraciones

- Estado: Aceptado
- Fecha: 2026-09-15
- Reemplaza a: —
- Reemplazado por: —

## Contexto

El dominio de RescueSync tiene un esquema relacional con dependencias claras
entre entidades: emergencias, lotes, convocatorias, ofertas (con sus
versiones), adjudicaciones y la bitácora de ejecución. Flask (ADR-002) no
trae ORM propio, así que hace falta elegir explícitamente cómo el código
Python va a mapear y consultar esas tablas, y cómo el equipo va a evolucionar
el esquema de base de datos a lo largo de las 5 entregas.

El riesgo concreto a resolver es que 5 personas van a tocar el esquema en
paralelo, cada una trabajando en su propio módulo de dominio. Sin
migraciones versionadas y sin un mapeo objeto-relacional compartido, los
cambios de esquema hechos por integrantes distintos van a chocar entre sí de
forma difícil de detectar y de revertir.

## Decisión

Se usa **SQLAlchemy 2.0.54** como capa de mapeo objeto-relacional, integrada
a Flask mediante **Flask-SQLAlchemy 3.1.1**, con **Alembic 1.20.0** como
motor de migraciones expuesto a través de **Flask-Migrate 4.1.0**. El driver
de conexión a PostgreSQL es **psycopg 3.3.5**.

Esta combinación es el estándar de facto del ecosistema Flask para proyectos
con base de datos relacional: da un ORM maduro y bien documentado,
migraciones versionadas que se revisan en PR como cualquier otro cambio de
código, y una integración directa con la app factory de Flask (sesiones de
base de datos atadas al ciclo de vida de la request, comandos de migración
disponibles vía CLI de Flask).

### Versión fijada

| Tecnología | Versión | Archivo del repositorio donde se fija |
|---|---|---|
| SQLAlchemy | `2.0.54` | `requirements.txt` |
| Flask-SQLAlchemy | `3.1.1` | `requirements.txt` |
| Alembic | `1.20.0` | `requirements.txt` |
| Flask-Migrate | `4.1.0` | `requirements.txt` |
| psycopg (driver) | `3.3.5` | `requirements.txt` |

## Alternativas consideradas

| Alternativa | A favor | En contra | Motivo del descarte |
|---|---|---|---|
| SQL crudo con psycopg directo | Control total sobre cada consulta, sin capa intermedia que aprender | Sin migraciones versionadas ni mapeo objeto-relacional: cada cambio de esquema se coordina a mano entre 5 personas, y las consultas se escriben y mantienen sin ninguna capa de validación o reuso compartida | Con cinco integrantes tocando el esquema en paralelo, la ausencia de migraciones versionadas es un riesgo de coordinación inmanejable; el costo de aprender SQLAlchemy es menor que el costo de coordinar cambios de esquema a mano |
| Peewee | ORM liviano, API simple, curva de entrada baja | Comunidad y documentación notablemente menores que las de SQLAlchemy; menos ejemplos, menos integraciones de terceros, menos respuestas disponibles ante problemas puntuales | Para un equipo que va a apoyarse en documentación y ejemplos para resolver dudas durante 5 entregas, se prioriza el ecosistema más grande y mejor documentado de SQLAlchemy |

## Consecuencias

### Positivas

- Los cambios de esquema quedan versionados como scripts de Alembic,
  revisables en PR igual que cualquier otro cambio de código, con un
  historial claro de quién cambió qué y cuándo.
- El mapeo objeto-relacional da un punto único de verdad sobre la forma de
  cada tabla (columnas, tipos, relaciones), reduciendo la duplicación de
  conocimiento del esquema entre módulos.
- Flask-SQLAlchemy y Flask-Migrate se integran directamente con los
  comandos de Flask, sin necesidad de scripts de infraestructura
  adicionales para correr migraciones.

### Negativas

- El equipo tiene que aprender la API de SQLAlchemy 2.0 (que difiere de
  versiones anteriores de la librería) además del flujo de Alembic para
  generar y revisar migraciones.
- Una migración mal generada o mal revisada puede romper el esquema de
  otro integrante; esto exige disciplina real de revisión de PRs que
  toquen modelos (ver `CONTRIBUTING.md`).

### Qué nos obliga a hacer

- Todo cambio de esquema se hace exclusivamente a través de una migración
  de Alembic generada con Flask-Migrate; está prohibido modificar el
  esquema de la base de datos a mano.
- Cada módulo de dominio define sus modelos en su propio archivo
  `modelos.py` dentro de `app/modulos/<modulo>/`, sin que otro módulo
  importe esos modelos directamente (la comunicación entre módulos pasa por
  la capa de `servicios`, según la regla de dependencias de
  `docs/arquitectura/componentes.md`).
- Toda migración nueva se revisa en PR antes de mergear a `main`, prestando
  atención especial a que no entre en conflicto con cambios de esquema de
  otro módulo.
