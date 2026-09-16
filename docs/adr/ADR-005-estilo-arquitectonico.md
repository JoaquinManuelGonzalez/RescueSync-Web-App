# ADR-005: Estilo arquitectónico

- Estado: Aceptado
- Fecha: 2026-09-15
- Reemplaza a: —
- Reemplazado por: —

## Contexto

El equipo tiene que elegir cómo organizar el sistema a nivel macro: cuántos
componentes desplegables tiene la app web, y cómo se estructura internamente
el código para que 5 personas puedan trabajar en paralelo sobre módulos de
dominio distintos sin pisarse.

Tres datos del contexto real del proyecto pesan sobre esta decisión. Primero,
el equipo es de 5 personas repartiendo trabajo entre 5 entregas con fechas
fijas (1/10, 22/10, 5/11 y 19/11 de 2026), lo que deja poco margen para
absorber la complejidad operativa de una arquitectura distribuida propia.
Segundo, el despliegue objetivo es local: un `docker compose up` que
cualquier integrante o la cátedra puedan correr sin infraestructura
adicional. Tercero, y más importante: el sistema **ya es distribuido** a
nivel de componentes externos, sin que la app web tenga que agregar más
fragmentación por su cuenta. Bonita corre como motor de procesos separado y
la API Nacional es un servicio REST en la nube (Entrega 3): esos son los
límites externos reales del sistema. El dashboard de indicadores, en
cambio, es un módulo más dentro de la propia aplicación web (se entrega al
final, pero no es un despliegue separado). La distribución real del sistema
ya viene dada por esos componentes externos, documentados en
`docs/arquitectura/componentes.md`.

## Decisión

Se adopta un **monolito modular** para la aplicación web (frontend + backend
Flask). Es un único proceso desplegable, organizado internamente en módulos
de dominio con fronteras claras y una regla de dependencias explícita (ver
`docs/arquitectura/componentes.md`), en lugar de una colección de servicios
desplegados por separado.

Esta decisión es consistente con el hecho de que la fragmentación real del
sistema ya existe a nivel de los componentes externos (Bonita, API
Nacional): partir además la app web interna en servicios independientes
agregaría una segunda capa de distribución sin ningún beneficio adicional,
sobre un equipo y un cronograma que no tienen margen para absorberla.

### Versión fijada

Este ADR no fija una versión de tecnología específica: es una decisión de
estilo arquitectónico que se apoya en las tecnologías ya fijadas en los
ADR-001 a ADR-004 (Flask, Jinja2, Tailwind, SQLAlchemy, PostgreSQL). La
consecuencia concreta y verificable es la estructura de carpetas y el
`docker-compose.yml` descriptos abajo, documentados en detalle en
`docs/arquitectura/componentes.md`.

## Alternativas consideradas

| Alternativa | A favor | En contra | Motivo del descarte |
|---|---|---|---|
| Microservicios | Escalado y despliegue independiente por servicio, aislamiento de fallos entre componentes propios | Sobrecarga de despliegue, comunicación de red interna y observabilidad distribuida (tracing, correlación entre servicios) sin ningún beneficio real en este contexto: el equipo es chico, el despliegue es local y no hay necesidad de escalar componentes internos por separado | El costo operativo de microservicios no tiene contrapartida en este proyecto; la complejidad de coordinación entre servicios propios se sumaría a la que ya existe con Bonita y la API Nacional, sin necesidad |
| Monolito sin módulos (todo en un mismo paquete, sin fronteras internas) | Más rápido de arrancar, sin overhead de definir convenciones de módulos | Con 5 personas escribiendo código en paralelo sobre el mismo paquete sin fronteras, el acoplamiento cruzado entre partes del dominio es prácticamente inevitable, y las revisiones de PR se vuelven más difíciles de razonar | La modularidad interna es la que permite que 5 personas avancen en paralelo sobre módulos de dominio distintos sin pisarse ni generar dependencias cruzadas no controladas |

## Consecuencias

### Positivas

- Un solo proceso desplegable simplifica el despliegue local y el que usa
  la cátedra para evaluar: no hace falta orquestar red ni descubrimiento de
  servicios entre partes propias del sistema.
- Las fronteras entre módulos de dominio (`usuarios_roles`, `emergencias`,
  `lotes_convocatorias`, `ofertas`, `adjudicacion`, `ejecucion_cierre`) dan
  al equipo la misma separación de responsabilidades que tendría con
  servicios separados, sin el costo operativo de desplegarlos por
  separado.
- La complejidad real de sistema distribuido (red, protocolos, fallos
  parciales) queda concentrada exactamente donde el enunciado la pone: en
  las integraciones con Bonita y la API Nacional, no en comunicación
  interna inventada por el equipo.

### Negativas

- Todos los módulos comparten el mismo proceso y el mismo ciclo de
  despliegue: un error de arranque en un módulo puede impedir levantar la
  aplicación completa.
- No hay escalado independiente por módulo; si en el futuro un módulo
  puntual necesitara escalar distinto del resto, habría que revisar esta
  decisión.

### Qué nos obliga a hacer

**Sobre el repositorio:**

- Un único repositorio Git para toda la app web (frontend y backend
  juntos), sin repositorios separados por módulo.
- Un único `requirements.txt` para todas las dependencias de Python del
  proyecto.
- Una carpeta por módulo de dominio dentro de `app/modulos/`, con la
  estructura interna documentada en `CONTRIBUTING.md` y en
  `docs/arquitectura/componentes.md`.
- La regla de dependencias entre módulos (documentada en
  `docs/arquitectura/componentes.md`) es de cumplimiento obligatorio y se
  revisa en cada PR que toque más de un módulo.

**Sobre el despliegue:**

- Un contenedor para la aplicación (`app`) y un contenedor para la base de
  datos (`db`), levantados con un único `docker compose up` desde la raíz
  del repositorio.
- Bonita y la API Nacional quedan fuera del `docker-compose.yml` de la app
  web: son componentes externos con su propio ciclo de vida, y la app web
  solo se integra con ellos por HTTP (ver `docs/arquitectura/componentes.md`).
