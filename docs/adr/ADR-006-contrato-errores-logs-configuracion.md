# ADR-006: Contrato de errores, logs y configuración

- Estado: Aceptado
- Fecha: 2026-09-15
- Reemplaza a: —
- Reemplazado por: —

## Contexto

RescueSync integra tres tipos de origen de error posible en cada operación:
errores de validación o de reglas de negocio propias, fallas o rechazos de
Bonita, y fallas o rechazos de la API Nacional. Sin un contrato único, cada
módulo terminaría devolviendo errores con forma distinta, dificultando tanto
la experiencia de quien usa la interfaz como el diagnóstico de un problema
que atraviesa varios componentes.

Además, diagnosticar una falla que involucra a Bonita o a la API Nacional
requiere poder rastrear una misma operación a través de los tres
componentes (app web, Bonita, API Nacional), y el sistema necesita
arrancar de forma segura sin depender de que alguien recuerde configurar
algo a mano en cada entorno (desarrollo local de cada integrante, entorno
de evaluación de la cátedra).

Este ADR fija la decisión estructural sobre estos tres contratos
transversales; el detalle operativo de cada uno (tablas de códigos,
política exacta de reintentos, formato exacto de cada campo de log, listado
completo de variables de entorno) se documenta por separado para no
sobrecargar este ADR con contenido que cambia con más frecuencia que una
decisión arquitectónica.

## Decisión

Se adoptan tres contratos transversales, obligatorios para todos los
módulos de la aplicación:

1. **Envelope único de error**: toda respuesta de error de la API expone la
   misma forma, con los campos `codigo`, `mensaje`, `detalle`, `timestamp`
   e `id_correlacion`. No se permite que un módulo devuelva errores con una
   forma distinta. El detalle completo (tabla de códigos HTTP e internos,
   política de reintentos ante fallas de Bonita y de la API Nacional) está
   en `docs/contratos/errores.md`.

2. **Logs JSON estructurados con identificador de correlación**: cada
   evento de log es una línea JSON con campos fijos, y toda operación que
   atraviesa más de un componente propaga el mismo identificador de
   correlación a través del encabezado HTTP `X-Correlation-Id`, tanto hacia
   Bonita como hacia la API Nacional. Ese identificador aparece en todos
   los logs de la operación y en el cuerpo de todo error que produzca. El
   detalle completo (campos obligatorios, qué datos nunca se registran,
   niveles de log) está en `docs/contratos/logging.md`.

3. **Configuración cien por ciento por variables de entorno, con fail
   fast**: ningún valor de configuración (credenciales, URLs de Bonita y de
   la API Nacional, parámetros de conexión a la base de datos, parámetros
   de reintento) se hardcodea en el código. La aplicación valida al
   arrancar que todas las variables obligatorias estén presentes, y falla
   inmediatamente si falta alguna, en vez de arrancar en un estado
   parcialmente configurado. El listado completo de variables, cuáles son
   obligatorias y la gestión de secretos están en
   `docs/contratos/configuracion.md` y en `.env.example`.

### Versión fijada

Este ADR no fija versión de una tecnología particular: es un contrato de
formato y de comportamiento que se implementa con las piezas ya elegidas en
otros ADRs (Flask para exponer las respuestas de error, la librería
estándar de Python para logging estructurado en JSON). El detalle operativo
completo de cada contrato vive en los documentos referenciados abajo, que
son los que efectivamente se implementan y se verifican en el código.

| Contrato | Documento de detalle |
|---|---|
| Envelope de error | `docs/contratos/errores.md` |
| Logging estructurado | `docs/contratos/logging.md` |
| Configuración por variables de entorno | `docs/contratos/configuracion.md`, `.env.example` |

## Alternativas consideradas

| Alternativa | A favor | En contra | Motivo del descarte |
|---|---|---|---|
| Cada módulo define su propio formato de error | Más rápido de escribir al principio, sin coordinación previa | Una interfaz o un consumidor de la API tendría que manejar formas de error distintas según el módulo que respondió, y depurar un error se vuelve más lento | Con 5 personas escribiendo módulos distintos en paralelo, un formato de error no unificado es exactamente el tipo de inconsistencia que esta épica busca prevenir |
| Logs de texto libre sin estructura | Más simple de escribir en el momento | Imposible de filtrar o correlacionar de forma confiable entre los tres componentes (app web, Bonita, API Nacional) cuando aparece un problema | El sistema atraviesa múltiples componentes externos; sin logs estructurados y correlacionados, diagnosticar una falla distribuida se vuelve inviable en la práctica |
| Configuración mezclada (algunos valores en código, otros en variables de entorno) | Menos archivos que tocar para un cambio rápido | Riesgo real de credenciales o URLs hardcodeadas terminando en el repositorio, y comportamiento distinto entre el entorno de un integrante y el de otro | El enunciado y la buena práctica de seguridad exigen que ningún secreto viva en el código; centralizar todo en variables de entorno con fail fast es la única forma de garantizar eso de manera verificable |

## Consecuencias

### Positivas

- Cualquier error que devuelva la aplicación tiene una forma predecible,
  sin importar qué módulo lo generó, lo que simplifica tanto el consumo
  desde la interfaz como la escritura de tests.
- Un problema que involucra a Bonita o a la API Nacional se puede rastrear
  de punta a punta siguiendo un único `id_correlacion` a través de los
  logs de los tres componentes.
- La aplicación nunca arranca en un estado a medio configurar: si falta
  una variable obligatoria, falla de inmediato con un mensaje claro, en vez
  de fallar más tarde de forma difícil de diagnosticar en medio de una
  operación real.

### Negativas

- Implementar el envelope único y el logging estructurado exige una capa
  transversal en `app/core/` (manejo de errores, logging, propagación del
  identificador de correlación) que todos los módulos tienen que usar de
  forma consistente, en vez de resolver logging o errores por su cuenta.
- El fail fast de configuración implica que un despliegue con una variable
  faltante no arranca en absoluto, lo cual es la conducta deseada pero
  exige que `.env.example` esté siempre completo y actualizado para que
  nadie pierda tiempo adivinando qué variable falta.

### Qué nos obliga a hacer

- Ningún módulo implementa su propio formato de error: todos usan la capa
  de manejo de errores de `app/core` que produce el envelope único.
- Todo cliente HTTP hacia Bonita o hacia la API Nacional propaga el
  encabezado `X-Correlation-Id` recibido (o generado si la request
  entrante no lo trae) y registra el log estructurado de la llamada
  saliente, éxito o error, según el formato de `docs/contratos/logging.md`.
- Ninguna credencial, URL de servicio externo ni parámetro de conexión se
  escribe en el código fuente; todo se lee desde variables de entorno
  declaradas (sin valor real) en `.env.example`.
- Toda variable de entorno nueva que se agregue a la aplicación se suma
  primero a `.env.example` y a la tabla de `docs/contratos/configuracion.md`,
  como parte del mismo PR que la introduce.
