# Registro de decisiones de arquitectura (ADR)

## Qué es un ADR y por qué lo usamos acá

Un ADR (Architecture Decision Record) es un documento corto que deja por
escrito una decisión de arquitectura importante: qué se decidió, en qué
contexto, qué alternativas se descartaron y por qué, y qué consecuencias
trae. No es documentación de diseño detallado ni un manual de uso: es un
registro histórico de decisiones, pensado para que alguien que se suma al
proyecto más adelante (un integrante nuevo, la cátedra, o el propio equipo
seis meses después) entienda por qué el sistema es como es, sin tener que
reconstruir la discusión de memoria.

En RescueSync los ADRs cumplen un rol concreto: el equipo es de 5 personas
arrancando módulos distintos en paralelo, sobre 5 entregas con fechas
fijas. El riesgo que resuelven es que cada integrante asuma un stack, una
versión o un criterio de diseño distinto al del resto. Cada ADR fija una
decisión de una vez, la versiona junto con el código, y evita que la misma
discusión se repita en cada módulo.

Todo ADR nuevo parte de la plantilla en [`ADR-000-plantilla.md`](./ADR-000-plantilla.md),
que define las secciones obligatorias: `Contexto`, `Decisión` (con la tabla
de versión fijada), `Alternativas consideradas` y `Consecuencias`.

## Índice de ADRs

| # | Título | Estado | Fecha | Documento |
|---|---|---|---|---|
| 000 | Plantilla de ADR | — | — | [ADR-000-plantilla.md](./ADR-000-plantilla.md) |
| 001 | Framework de frontend | Aceptado | 2026-09-15 | [ADR-001-framework-frontend.md](./ADR-001-framework-frontend.md) |
| 002 | Framework de backend | Aceptado | 2026-09-15 | [ADR-002-framework-backend.md](./ADR-002-framework-backend.md) |
| 003 | ORM y migraciones | Aceptado | 2026-09-15 | [ADR-003-orm.md](./ADR-003-orm.md) |
| 004 | Motor de base de datos | Aceptado | 2026-09-15 | [ADR-004-motor-base-de-datos.md](./ADR-004-motor-base-de-datos.md) |
| 005 | Estilo arquitectónico | Aceptado | 2026-09-15 | [ADR-005-estilo-arquitectonico.md](./ADR-005-estilo-arquitectonico.md) |
| 006 | Contrato de errores, logs y configuración | Aceptado | 2026-09-15 | [ADR-006-contrato-errores-logs-configuracion.md](./ADR-006-contrato-errores-logs-configuracion.md) |
| 007 | Estructura del esqueleto ejecutable y cadena de build de frontend | Propuesto | 2026-09-17 | [ADR-007-estructura-esqueleto-ejecutable.md](./ADR-007-estructura-esqueleto-ejecutable.md) |
| 008 | Gestión de dependencias de Python con uv | Propuesto | 2026-09-17 | [ADR-008-gestion-dependencias-uv.md](./ADR-008-gestion-dependencias-uv.md) |
| 009 | Autenticación por sesión y control de accesos basado en roles | Propuesto | 2026-09-21 | [ADR-009-autenticacion-y-rbac.md](./ADR-009-autenticacion-y-rbac.md) |

La numeración es correlativa y nunca se reutiliza: si un ADR queda
reemplazado u obsoleto, su número no vuelve a asignarse a una decisión
distinta. El siguiente ADR que se escriba, sea nuevo o reemplace a uno
existente, usa el número `010` en adelante.

## Ciclo de vida de un ADR

Un ADR pasa por los siguientes estados, en este orden:

```
Propuesto → Aceptado → Reemplazado por ADR-XXX
                     └→ Obsoleto
```

- **Propuesto**: la decisión está redactada y en discusión por el equipo,
  todavía no es la decisión vigente del proyecto. Un ADR en este estado
  puede editarse libremente mientras se afina la discusión.
- **Aceptado**: el equipo cerró la decisión y el código del repositorio ya
  la refleja (o va a reflejarla en el PR que introduce el ADR). A partir de
  este momento el ADR es **inmutable** (ver regla abajo).
- **Reemplazado por ADR-XXX**: la tecnología o el criterio que este ADR
  fijaba cambió, y la decisión vigente ahora vive en un ADR nuevo,
  identificado por su número. El ADR reemplazado queda en el repositorio
  como registro histórico.
- **Obsoleto**: la decisión dejó de aplicar (por ejemplo, porque el
  componente al que se refería se eliminó del sistema) sin que haya un ADR
  nuevo que la reemplace directamente.

## Regla de inmutabilidad

**Un ADR en estado `Aceptado` nunca se edita.** Esto es deliberado: un ADR
es un registro histórico de una decisión tomada en un momento y un contexto
determinados. Editar su contenido después de aceptado le hace perder valor
como registro, porque ya no refleja fielmente qué se pensó y por qué en el
momento en que se tomó la decisión.

Si el equipo decide cambiar una tecnología o un criterio que ya estaba
fijado en un ADR aceptado, el procedimiento es siempre el mismo:

1. Se escribe un **ADR nuevo**, con el siguiente número correlativo
   disponible, que documenta la nueva decisión con sus propios `Contexto`,
   `Decisión`, `Alternativas consideradas` y `Consecuencias`. En el campo
   `Reemplaza a` de este ADR nuevo se pone el número del ADR anterior.
2. En el ADR **anterior**, aceptado, se modifica **únicamente** el campo
   `Estado` (pasa a `Reemplazado por ADR-XXX`, con el número del ADR nuevo)
   y el campo `Reemplazado por` (se completa con ese mismo número). El
   resto del documento -- `Contexto`, `Decisión`, `Alternativas
   consideradas`, `Consecuencias` -- **no se toca**: queda exactamente como
   estaba cuando se aceptó, como registro fiel de lo que se pensó en su
   momento.
3. Ambos ADRs se agregan o actualizan en la tabla del índice de este
   documento, y el ADR nuevo referencia al anterior en su propio
   `Contexto` si hace falta explicar por qué cambió la decisión.

### Ejemplo concreto paso a paso

Supongamos que, avanzada la Entrega 3, el equipo descubre que Python 3.14
no tiene wheel binario disponible para una dependencia crítica en el
entorno de la cátedra, y decide bajar a Python 3.12. El ADR-002 ya está
`Aceptado` y ya fija Python 3.14, así que no se edita: se sigue el
procedimiento.

1. Se crea `ADR-007-actualizacion-version-python.md`, con:
   - `Estado: Aceptado`
   - `Reemplaza a: ADR-002`
   - `Reemplazado por: —`
   - Un `Contexto` que explica el problema encontrado (falta de wheel
     binario para Python 3.14 en el entorno de evaluación).
   - Una `Decisión` que fija Python 3.12 como nueva versión, con su propia
     tabla de versión fijada (`.python-version`, `Dockerfile`).
   - Sus propias `Alternativas consideradas` (por ejemplo, compilar la
     dependencia desde fuente en 3.14, descartada por el costo de
     mantenimiento del build) y `Consecuencias`.

2. En `ADR-002-framework-backend.md`, el único cambio permitido es en el
   encabezado:

   ```diff
   - Estado: Aceptado
   + Estado: Reemplazado por ADR-007
     Fecha: 2026-09-15
     Reemplaza a: —
   - Reemplazado por: —
   + Reemplazado por: ADR-007
   ```

   Las secciones `Contexto`, `Decisión`, `Alternativas consideradas` y
   `Consecuencias` de `ADR-002-framework-backend.md` quedan exactamente
   como estaban: siguen diciendo Python 3.14, porque eso es lo que
   realmente se pensó y se decidió en su momento. No se corrige ese
   contenido para que "coincida" con la nueva decisión.

3. Se actualiza la tabla del índice de este `README.md`: la fila `002`
   pasa a estado `Reemplazado por ADR-007`, y se agrega una fila nueva
   `007` con estado `Aceptado`.

Este procedimiento es el mismo sin importar qué ADR cambie, y es el que
mantiene el historial de decisiones confiable a lo largo de las 5 entregas.

## Enmienda parcial

El procedimiento de arriba asume que la decisión de fondo de un ADR cambió por
completo. En la práctica aparece un caso intermedio: un ADR nuevo contradice
**una cláusula puntual** de un ADR aceptado, mientras el resto de esa decisión
sigue plenamente vigente.

El ejemplo real es el ADR-008: cambia dónde se declaran las dependencias de
Python, cláusula que fijaban el ADR-002 y el ADR-005. Pero el ADR-002 también
decidió Flask y Python 3.14, y el ADR-005 decidió el monolito modular, y nada
de eso cambió. Marcar esos dos ADRs como `Reemplazado por ADR-008` sería
falso: daría a entender que Flask o el monolito modular dejaron de estar
vigentes.

En ese caso el procedimiento es:

1. El ADR nuevo se escribe igual que cualquier otro, pero deja `Reemplaza a:
   —`, porque no reemplaza nada.
2. El ADR nuevo incluye una sección final **`Relación con ADRs previos`** que
   nombra, uno por uno, cada ADR afectado y **cita la cláusula exacta** que
   enmienda, indicando explícitamente qué de ese ADR sigue vigente.
3. El ADR nuevo abre con una nota al pie del encabezado que remite a esa
   sección, para que nadie lo lea como una decisión aislada.
4. El ADR anterior **no se toca en absoluto**: ni su contenido ni su `Estado`.
   Sigue en `Aceptado`, porque sigue siendo la decisión vigente en todo lo
   demás.
5. En el índice de este documento, el ADR anterior tampoco cambia de estado.

La diferencia práctica con el reemplazo es esta: en un reemplazo, el ADR viejo
deja de aplicar y queda como registro histórico; en una enmienda parcial, el
ADR viejo **sigue vigente** y hay que leerlo junto con el que lo enmienda.

Ante la duda entre enmendar parcialmente y reemplazar, vale esta regla: si
después del ADR nuevo alguien todavía necesita leer el viejo para saber qué
hacer, es enmienda parcial; si el viejo ya no le sirve para nada, es
reemplazo.
