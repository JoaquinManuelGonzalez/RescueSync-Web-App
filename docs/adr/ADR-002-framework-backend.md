# ADR-002: Framework de backend

- Estado: Aceptado
- Fecha: 2026-09-15
- Reemplaza a: —
- Reemplazado por: —

## Contexto

RescueSync necesita un backend que resuelva tres tipos de trabajo distinto
a la vez: servir interfaces web renderizadas del lado del servidor para
cuatro roles de usuario (ver ADR-001), persistir el dominio local de
emergencias, lotes, convocatorias, ofertas y adjudicaciones, e integrarse
por HTTP a medida con dos sistemas externos que el equipo no controla:
Bonita (instanciación de procesos, tareas humanas, y el callback que Bonita
dispara al vencer la ventana de ofertas) y la API Nacional (validación de
habilitación, reserva y liberación de recursos, autenticada con JWT).

El equipo de 5 personas necesita elegir un lenguaje y un framework en el
que todos puedan avanzar en paralelo sin curva de aprendizaje alta, que
tenga soporte maduro para HTTP saliente configurable (timeouts, reintentos,
backoff) porque esas integraciones son la parte más riesgosa del sistema, y
que no imponga estructura de más para un problema que no la necesita.

## Decisión

Se usa **Python 3.14** con **Flask 3.1.3** como framework web. Flask es un
microframework: no impone ORM, capa de admin ni estructura de proyecto, lo
que deja al equipo definir su propia organización modular (ver ADR-005 y
`docs/arquitectura/componentes.md`) ajustada exactamente a los 6 módulos de
dominio que pide el enunciado, sin cargar con piezas que el proyecto no usa.

Python se elige por sobre otros lenguajes porque el equipo tiene más
experiencia previa en él, lo cual reduce el riesgo de las 5 entregas con
fecha fija: no hay tiempo de sobra para que alguien aprenda un lenguaje
nuevo a la vez que resuelve integraciones HTTP no triviales.

### Versión fijada

| Tecnología | Versión | Archivo del repositorio donde se fija |
|---|---|---|
| Python | `3.14` | `.python-version`, `Dockerfile` |
| Flask | `3.1.3` | `requirements.txt` |

## Alternativas consideradas

| Alternativa | A favor | En contra | Motivo del descarte |
|---|---|---|---|
| Django | Batería completa incluida (ORM, admin, autenticación), productividad alta en CRUDs estándar | El ORM y el panel de administración vienen atados a las convenciones del framework; el enunciado exige integración HTTP a medida con Bonita y la API Nacional, terreno donde el peso adicional de Django no aporta valor | Se prefiere un framework liviano que no obligue a trabajar contra las convenciones de Django para las partes no estándar del sistema (los clientes HTTP de integración) |
| FastAPI | Muy orientado a APIs, validación de esquemas moderna, tipado nativo | Está pensado para servir una API pura; el renderizado de formularios y pantallas del lado del servidor (Jinja2, ver ADR-001) queda enteramente a cargo del equipo, sin las convenciones de vistas que sí trae Flask | El grueso de RescueSync es interfaz web server-side, no una API pública; FastAPI resolvería bien la parte de API pero no aporta nada extra para la parte de renderizado, que es mayoritaria |
| Node.js / Express | Buen soporte de I/O asincrónico para llamadas HTTP salientes | El equipo tiene menos experiencia en el ecosistema Node/JavaScript en el backend que en Python | Se prioriza el lenguaje en el que el equipo ya tiene más rodaje, dado el riesgo de tiempo de las 5 entregas |
| .NET | Framework maduro, tipado fuerte, buen soporte de HTTP clients | El equipo tiene menos experiencia previa en C#/.NET que en Python | Mismo motivo que Node/Express: se prioriza la curva de aprendizaje más baja para el equipo actual |

## Consecuencias

### Positivas

- El equipo trabaja en el lenguaje que mejor conoce, lo que reduce el
  riesgo de atraso frente a las fechas fijas de entrega.
- Flask no impone una estructura de proyecto propia, lo que permite adoptar
  directamente la organización en módulos de dominio que exige el
  enunciado (ver ADR-005), sin pelear contra las convenciones del
  framework.
- Al no traer ORM propio, la elección de SQLAlchemy (ADR-003) es una
  decisión explícita y documentada, no un valor por defecto heredado del
  framework.

### Negativas

- A diferencia de Django, no hay panel de administración ni ORM incluidos:
  cada pieza (ORM, migraciones, autenticación, formularios) se elige y se
  cablea a mano, lo que implica más decisiones explícitas a tomar (varias
  de ellas ya resueltas en ADRs propios).
- Python 3.14 es una versión reciente; existe riesgo de que alguna
  dependencia todavía no tenga wheel binario disponible y requiera
  compilación al instalar. Este riesgo se valida en la épica del esqueleto
  ejecutable; si aparece un problema real, se resuelve con un ADR nuevo que
  reemplace a este (ver `docs/adr/README.md` para el procedimiento de
  reemplazo).

### Qué nos obliga a hacer

- Toda dependencia de Python del proyecto se declara con versión exacta en
  `requirements.txt`; no se permiten instalaciones sin versión fijada.
- La versión de Python del entorno de desarrollo y del contenedor tiene que
  coincidir con la declarada en `.python-version` y en el `Dockerfile`.
- Los clientes HTTP hacia Bonita y la API Nacional se implementan como
  módulos propios dentro de `app/core/integraciones/`, no como llamadas
  sueltas desde cualquier parte del código (ver regla de dependencias en
  `docs/arquitectura/componentes.md`).
