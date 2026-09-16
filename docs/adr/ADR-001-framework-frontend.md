# ADR-001: Framework de frontend

- Estado: Aceptado
- Fecha: 2026-09-15
- Reemplaza a: —
- Reemplazado por: —

## Contexto

RescueSync es una aplicación web con cuatro roles (Operador Municipal, Centro
Coordinador Regional, Representante de ONG, Auditor/Directivo) cuyo uso
principal son pantallas de gestión y formularios: alta de emergencias, carga
de lotes y convocatorias, carga y revisión de ofertas, y adjudicación. El
equipo es de 5 personas trabajando en paralelo sobre 5 entregas con fechas
fijas, y el enunciado no exige que la interfaz consuma una API propia desde
un cliente separado: el backend en Flask ya tiene que resolver la lógica de
negocio y la integración con Bonita y la API Nacional.

Hace falta elegir con qué se renderiza el HTML y con qué se le da estilo,
de forma que el costo de aprendizaje y de mantenimiento sea bajo para un
equipo que no es de cinco desarrolladores frontend dedicados, y que el
resultado sea consistente entre módulos escritos por personas distintas.

## Decisión

Se usa **Jinja2** para el renderizado de plantillas del lado del servidor
(server-side rendering) y **Tailwind CSS** para el estilo visual. Jinja2 no
es una elección adicional: viene incluido con Flask, que ya es el framework
de backend elegido (ver ADR-002), así que no suma una dependencia nueva ni
una decisión independiente de stack.

Es importante remarcar que **Tailwind es un framework de CSS, no de
JavaScript**: no introduce un runtime de componentes ni cambia el modelo de
renderizado. La generación de HTML sigue siendo enteramente responsabilidad
de Jinja2 en el servidor; Tailwind solo aporta las clases utilitarias con
las que se escribe el estilo de esas plantillas. Si más adelante aparece una
necesidad puntual de interactividad en el navegador (por ejemplo, mostrar u
ocultar un bloque de un formulario, validar un campo antes de enviar), se
resuelve con JavaScript vanilla embebido en la plantilla correspondiente. Si
esa necesidad crece hasta requerir un patrón más estructurado (estado
compartido entre componentes, enrutamiento en el cliente, etc.), se evalúa
en un ADR posterior; hoy no hay ningún requisito del enunciado que lo
justifique.

Tailwind requiere Node.js para su cadena de build (generar el CSS final a
partir de las clases usadas en las plantillas). Esta máquina de desarrollo
no tiene Node instalado todavía; la resolución concreta de esa cadena de
build (Node dockerizado o no, script de build, watch en desarrollo) queda a
cargo de la épica del esqueleto ejecutable, que es la que crea `Dockerfile`,
`docker-compose.yml` y los archivos de configuración de Node. Este ADR deja
fijada la decisión de tecnología y de versión; no resuelve la mecánica de
build.

### Versión fijada

| Tecnología | Versión | Archivo del repositorio donde se fija |
|---|---|---|
| Jinja2 | la que fije Flask 3.1.3 como dependencia (ver ADR-002) | `requirements.txt` |
| Tailwind CSS | `4.3.3` | `package.json` / `package-lock.json` |
| Node.js | versión a definir por el equipo, documentada como runtime de build | `.nvmrc` |

## Alternativas consideradas

| Alternativa | A favor | En contra | Motivo del descarte |
|---|---|---|---|
| SPA con React o Vue | Interactividad rica en el cliente, ecosistema de componentes | Duplica el stack (frontend y backend con lenguajes/herramientas distintas), exige exponer una API REST completa solo para el consumo propio de la SPA, y suma un build separado del de Tailwind | Para 5 personas en 5 entregas donde el grueso del trabajo son formularios de gestión, el costo de mantener dos stacks y una API interna no se justifica frente al beneficio |
| Bootstrap | Componentes prearmados, curva de entrada baja | Menos control fino de diseño que con utilidades, y el CSS que trae por defecto no se purga: se termina enviando estilo muerto que no se usa | Tailwind da el mismo punto de partida rápido con clases utilitarias y, al purgar las clases no usadas en el build, evita el CSS muerto que Bootstrap arrastra |
| CSS escrito a mano | Control total, cero dependencias de build | Costo de mantenimiento alto cuando 5 personas escriben CSS en paralelo sin convenciones compartidas: nombres de clases inconsistentes, duplicación de reglas, difícil de revisar en PRs | El equipo prioriza consistencia entre módulos escritos por integrantes distintos por sobre el control total que da el CSS a mano |

## Consecuencias

### Positivas

- Un solo lugar donde vive el HTML (las plantillas Jinja2 dentro de cada
  módulo Flask), sin sincronizar dos capas de renderizado.
- Tailwind da consistencia visual entre pantallas hechas por integrantes
  distintos sin necesidad de un sistema de diseño propio construido desde
  cero.
- No se necesita exponer una API REST completa para consumo interno del
  propio frontend; el backend solo expone lo que efectivamente necesitan
  Bonita y la API Nacional (ver `docs/arquitectura/componentes.md`).

### Negativas

- Cualquier interactividad rica en el navegador requiere JavaScript vanilla
  escrito a mano, sin las comodidades de un framework de componentes.
- El equipo depende de tener Node instalado (o dockerizado) para generar el
  CSS final; sin ese paso, las clases de Tailwind usadas en las plantillas
  no se traducen en estilos reales.

### Qué nos obliga a hacer

- Las plantillas Jinja2 se ubican dentro de cada módulo (`app/modulos/<modulo>/plantillas/`)
  más una carpeta compartida (`app/plantillas/`) para el layout base y los
  parciales comunes, según la estructura documentada en `CONTRIBUTING.md`.
- Toda clase de Tailwind usada en el proyecto tiene que pasar por el proceso
  de build antes de llegar a producción; no se editan archivos CSS
  compilados a mano.
- Cualquier propuesta de sumar un framework de JavaScript en el cliente
  requiere un ADR nuevo que justifique por qué JS vanilla ya no alcanza.
