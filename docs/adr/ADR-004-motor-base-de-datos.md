# ADR-004: Motor de base de datos

- Estado: Aceptado
- Fecha: 2026-09-15
- Reemplaza a: —
- Reemplazado por: —

## Contexto

RescueSync necesita persistir el dominio local (usuarios y roles,
emergencias, lotes, convocatorias, ofertas y sus versiones, adjudicaciones y
bitácora de ejecución) en una base de datos relacional. El enunciado de la
cátedra pide explícitamente que el sistema resuelva locking y control de
concurrencia sobre los recursos en disputa (varias ONGs pueden ofertar sobre
el mismo lote, y la adjudicación tiene que resolverse de forma consistente),
y la cátedra recomienda de forma explícita usar PostgreSQL, otorgando
además puntaje extra por dockerizarlo.

El equipo tiene 5 integrantes trabajando cada uno en su propia máquina, más
un entorno de evaluación de la cátedra: hace falta que la base de datos se
levante igual en todos los entornos, sin depender de que cada persona instale
y configure PostgreSQL a mano con el riesgo de versiones o configuraciones
distintas entre máquinas.

## Decisión

Se usa **PostgreSQL 18** corriendo en un contenedor Docker, con la imagen
oficial **`postgres:18-trixie`**. El servicio se define con el nombre `db`
dentro de `docker-compose.yml` en la raíz del repositorio, con un volumen
Docker nombrado para persistir los datos entre reinicios del contenedor, y
con las credenciales (usuario, contraseña, nombre de base de datos, puerto)
tomadas de variables de entorno declaradas en `.env.example` (sin valores
reales), consistente con el contrato de configuración del ADR-006.

Esta decisión responde directamente a dos puntos que la cátedra evalúa de
forma explícita: primero, que PostgreSQL es el motor recomendado por la
cátedra; segundo, que dockerizarlo otorga puntaje extra en la evaluación.
Además, PostgreSQL da soporte maduro de locking a nivel de fila
(`SELECT ... FOR UPDATE`) y de transacciones con niveles de aislamiento
configurables, que es exactamente el mecanismo que el enunciado pide usar
para evitar condiciones de carrera en la adjudicación de ofertas.

### Versión fijada

| Tecnología | Versión | Archivo del repositorio donde se fija |
|---|---|---|
| PostgreSQL | `18` (imagen `postgres:18-trixie`) | `docker-compose.yml` (servicio `db`) |
| Credenciales y parámetros de conexión | variables de entorno | `.env.example` |

## Alternativas consideradas

| Alternativa | A favor | En contra | Motivo del descarte |
|---|---|---|---|
| PostgreSQL instalado directamente en cada máquina | Sin overhead de Docker, acceso directo al binario local | Cinco entornos de desarrollo divergentes en versión y configuración, que es exactamente el problema que esta épica de decisiones busca eliminar | Dockerizar la base de datos es la forma de garantizar que los 5 integrantes y el entorno de evaluación de la cátedra corran la misma versión con la misma configuración |
| SQLite | Cero configuración, un solo archivo, ideal para prototipos rápidos | No ofrece locking ni control de concurrencia real a nivel de fila para escrituras simultáneas, y la cátedra recomienda explícitamente PostgreSQL | El enunciado pide locking y control de concurrencia como requisito de dominio (disputas de ofertas sobre el mismo lote); SQLite no cubre esa necesidad |
| MySQL / MariaDB | Motor relacional maduro, también ampliamente usado | La cátedra recomienda explícitamente PostgreSQL y otorga puntaje extra específicamente por dockerizar PostgreSQL, no un motor genérico | No hay ninguna ventaja técnica que compense apartarse de la recomendación explícita de la cátedra y perder el puntaje extra asociado |

## Consecuencias

### Positivas

- Los 5 integrantes y el entorno de evaluación de la cátedra corren
  exactamente la misma versión de PostgreSQL con la misma configuración,
  eliminando el problema de entornos divergentes.
- Se obtiene el puntaje extra que la cátedra otorga por dockerizar
  PostgreSQL.
- PostgreSQL da las herramientas de locking y control de concurrencia que
  el enunciado exige para resolver disputas sobre el mismo lote de forma
  consistente.
- La persistencia sobrevive a la recreación del contenedor de aplicación
  gracias al volumen nombrado, sin depender del ciclo de vida del
  contenedor `app`.

### Negativas

- Cada integrante necesita tener Docker funcionando en su máquina para
  poder levantar la base de datos localmente.
- El acceso directo a la base (por ejemplo con un cliente SQL de
  escritorio) requiere primero conocer el puerto y las credenciales
  publicadas por el contenedor, en vez de conectarse a un servicio ya
  instalado en el sistema operativo.

### Qué nos obliga a hacer

- El servicio `db` se define en `docker-compose.yml` en la raíz del
  repositorio, nunca en un compose separado ni embebido en otro archivo.
- Ninguna credencial de base de datos se hardcodea en el código ni en
  `docker-compose.yml`: todas se leen de variables de entorno declaradas en
  `.env.example` sin valores reales (ver ADR-006 y
  `docs/contratos/configuracion.md`).
- Toda operación que dispute un recurso compartido (por ejemplo, adjudicar
  un lote entre varias ofertas) tiene que usar explícitamente locking a
  nivel de fila o una transacción con el nivel de aislamiento adecuado; no
  alcanza con validar en la capa de aplicación sin protección a nivel de
  base de datos.
- El contenedor `db` de PostgreSQL es parte exclusiva del `docker-compose.yml`
  de la app web; Bonita y la API Nacional quedan fuera de ese compose (ver
  ADR-005).
