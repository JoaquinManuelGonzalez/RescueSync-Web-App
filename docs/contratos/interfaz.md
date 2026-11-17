# Contrato de interfaz

Cómo se conecta una pantalla de RescueSync con el backend y con qué piezas se arma. La decisión
de tecnología (Jinja2 + Tailwind CSS 4, JS vanilla) está en
[ADR-001](../adr/ADR-001-framework-frontend.md).

## 1. La base: los templates del equipo

La base visual la definió el equipo en `frontend/plantillas/` y en `frontend/src/input.css`
(paleta en `@theme`, animaciones `fade` y `fade-up`, `estaticos/css/flash.css`). **Se respeta
tal cual**: una integración con el backend conecta esos templates, no los rediseña.

| Template | Qué es | Qué se le agregó para conectarlo |
|---|---|---|
| `layout.html` | Layout de todas las pantallas: navbar con sesión, mensajes flash arriba, bloques `title` y `content` | `<meta name="csrf-token">` y `interfaz.js` en el `<head>`; en cada mensaje flash, la cruz para cerrarlo y `data-alerta-descartable` para que se vaya solo; `data-minutos-sesion` en el `<body>` |
| `navbar.html` | Logo, campana de notificaciones, menú de perfil, menú mobile | Enlaces de sección ("Inicio" más una por cada `entradas_de_menu()`, en desktop y en el menú mobile, marcando la actual); enlaces reales (logo → inicio, "Mi perfil"); "Cerrar sesión" pasó de `<a>` a un formulario POST con CSRF, con las mismas clases, porque el servidor no acepta cerrar sesión por GET |
| `login.html` | Bienvenida con el ingreso: presentación de la app a un lado y formulario al otro (apilados en mobile) | `action`, token CSRF, campo `email` (el backend autentica por email), `next`, y el botón para mostrar u ocultar la contraseña. Se arma con los macros `campo()` / `boton_envio()` y `data-envio-con-carga`; no hay recuperación de contraseña: una leyenda indica pedírsela a un administrador |
| `hub.html` | Panel de inicio: saludo con rol y organización, y una tarjeta por sección | Las tarjetas salen de `entradas_de_menu()` (sección 4) con su título y descripción; un perfil sin pantallas todavía ve un estado vacío |
| `cargar_oferta.html`, `inventario.html`, `notificaciones.html`, `inicio.html` | Maquetas de épicas siguientes | Nada |

Las categorías de los mensajes flash son las que dibuja `layout.html`: `success`, `error`,
`warning` e `info` (constantes `EXITO`, `ERROR`, `ADVERTENCIA`, `INFO` de `app.core.interfaz.vistas`).
Los mensajes se cierran con su cruz o solos: 5 s los de éxito, 6 s los informativos, 8 s las
advertencias y 10 s los errores; con el mouse encima, la cuenta se detiene.

## 2. Pantallas de gestión y sus componentes

Las pantallas nuevas de la épica de identidad (cuentas, organizaciones, perfil, cambio de
contraseña, página de error) extienden `layout.html` y se arman con componentes reutilizables,
para no repetir listas largas de clases en cada una:

```
frontend/
├── src/componentes/*.css          clases de componente (importadas desde input.css)
├── estaticos/js/interfaz.js       comportamiento por data-attributes
└── plantillas/
    ├── componentes/               macros Jinja
    ├── usuarios/, organizaciones/, sesion/, errores/
```

### 2.1 Clases (`src/componentes/`)

Tomadas de las clases que ya usaban los templates del equipo (`bg-primario`,
`hover:bg-acento/50`, tarjetas blancas con `ring-gray-200`…).

| Familia | Clases |
|---|---|
| Botones | `.btn` + `.btn-primario`, `.btn-secundario`, `.btn-peligro`, `.btn-fantasma`; `.btn-bloque`, `.btn-icono`; `.spinner` |
| Formularios | `.formulario`, `.formulario-grilla`, `.formulario-acciones`, `.campo`, `.campo-etiqueta`, `.campo-control` (en un `<select>` lleva su propio chevron, alineado), `.campo-control-invalido`, `.campo-error`, `.campo-ayuda`, `.campo-contrasena`, `.campo-contrasena-alternar`, `.requisitos-contrasena`, `.barra-filtros`, `.campo-filtro` |
| Superficies | `.pagina`, `.pagina-angosta`, `.pagina-encabezado`, `.pagina-titulo`, `.pagina-subtitulo`, `.tarjeta`, `.tarjeta-cuerpo`, `.tarjeta-titulo`, `.icono-circular`, `.estado-vacio`, `.lista-datos` |
| Tablas | `.tabla-contenedor`, `.tabla`, `.tabla-encabezado`, `.tabla-fila`, `.tabla-celda`, `.tabla-acciones`, `.paginacion`, `.paginacion-enlace`, `.paginacion-actual` |
| Insignias | `.insignia` + `.insignia-primaria`, `-exito`, `-neutra`, `-advertencia`, `-error`, `-info` |
| Avisos fijos | `.alerta` + `.alerta-exito`, `-error`, `-advertencia`, `-info` (mismo estilo que los flash) |
| Modal | `.modal`, `.modal-panel`, `.modal-encabezado`, `.modal-icono`, `.modal-titulo`, `.modal-texto`, `.modal-acciones` |
| Destacados | `.hero`, `.hero-titulo`, `.hero-texto`, `.hero-etiquetas`, `.hero-etiqueta`; `.rasgo` (+ `-icono`, `-titulo`, `-texto`); `.cifra` (+ `-valor`, `-texto`); `.animar-escalonado` (los hijos entran en cascada) |
| Accesos | `.accesos-grilla`, `.acceso`, `.acceso-icono`, `.acceso-cuerpo`, `.acceso-titulo`, `.acceso-texto`, `.acceso-flecha` |
| Bienvenida | `.bienvenida`, `.bienvenida-presentacion`, `.bienvenida-marca`, `.bienvenida-logo`, `.bienvenida-rasgos`, `.bienvenida-cifras`, `.bienvenida-acceso`, `.bienvenida-acceso-titulo`, `.bienvenida-acceso-texto`, `.bienvenida-nota` |
| Indicadores (panel de auditoría) | `.periodo-cabecera` (+ `-icono`, `-titulo`, `-texto`), `.periodo-atajos`, `.periodo-atajo`, `.periodo-atajo-activo`, `.periodo-filtro`, `.periodo-filtro-accion`, `.periodo-resumen`; `.kpi-grilla`, `.kpi` + tono `.kpi-primario`, `-info`, `-exito`, `-advertencia`; `.kpi-cabecera`, `.kpi-etiqueta`, `.kpi-icono`, `.kpi-valor`, `.kpi-valor-sin-dato`, `.kpi-pie`, `.kpi-detalle`, `.kpi-porcentaje`, `.kpi-barra`, `.kpi-barra-relleno`, `.kpi-nota`; `.panel-pestanas`, `.panel-pestana`, `.panel-pestana-activa`; `.seccion-cabecera`, `.seccion-titulo`, `.seccion-texto`; `.filtro-segmentado`, `.filtro-segmento`, `.filtro-segmento-activo`, `.gravedad-punto` + `-baja`, `-media`, `-alta`, `-critica`; `.decision-punto` + `-reapertura`, `-continuar_parcial` (mismos tonos que las barras de decisiones), `.decisiones-lista` (insignias de las decisiones de una emergencia); `.graficos-grilla` (+ `-ancha`, `-angosta`), `.grafico-tarjeta`, `.grafico-cabecera`, `.grafico-titulo`, `.grafico-descripcion`, `.grafico-cuerpo`, `.grafico-lienzo`, `.grafico-centro` (+ `-cifra`, `-texto`), `.grafico-respaldo`, `.grafico-vacio` (+ `-icono`), `.grafico-leyenda` (+ `-item`, `-marca`, `-texto`, `-valor`), `.grafico-tono-exito`, `.grafico-tono-advertencia`, `.grafico-tono-primario`, `.grafico-tono-serie-1` a `-8` (paleta categórica de `graficos.js`), `.grafico-nota`, `.grafico-cabecera-fila`, `.graficos-grilla-pareja` (dos gráficos lado a lado desde tablet); `.kpi-grilla-tres` (tres cifras sin tarjeta huérfana en tablet); `.seccion-cabecera-apilada` (filtros debajo del título); `.cobertura-barra` (+ `-fila`, `-relleno`, `-valor`), `.rubro-punto`; `.gravedad-tarjetas`, `.gravedad-tarjeta` (+ `-cabecera`, `-nombre`, `-plazo`, `-cifra`, `-sin-dato`, `-texto`), `.gravedad-relleno-baja` / `-media` / `-alta` / `-critica`; `.exportar-menu`, `.exportar-boton` (+ `-flecha`), `.exportar-opciones`, `.exportar-opcion` (+ `-formato`, `-texto`); `.tabla-orden` (+ `-activo`, `-icono`), `.ranking-posicion` (+ `-podio`), `.ranking-ong`, `.ranking-cifra`, `.ranking-sin-dato`; `.seccion-error` (+ `-icono`, `-textos`, `-titulo`, `-mensaje`); `.esqueleto` (+ `-titulo`, `-texto`, `-lienzo`, `-tarjeta`) |

**Las tablas no tienen scroll horizontal.** En pantallas anchas el texto largo se parte dentro
de su celda; por debajo de `md` cada fila se apila como una tarjeta y cada dato muestra su
título (el `data-etiqueta` que pone el macro `celda()`). Todo listado va paginado.

### 2.2 Macros (`plantillas/componentes/`)

| Archivo | Macros |
|---|---|
| `iconos.html` | `icono(nombre, clase="size-5")`, `spinner()` — íconos outline de 24×24, del mismo tipo que los de `inventario.html` |
| `formularios.html` | `csrf()`, `campo(field, opciones, vacia, ayuda, atributos, requisitos)`, `boton_envio(...)`, `formulario_accion(...)`, `filtro_texto(...)`, `filtro_select(...)` |
| `tablas.html` | `tabla(columnas)` y `celda(etiqueta)` (con `{% call %}`), `paginacion(pagina)` |
| `alertas.html` | `alerta(categoria, mensaje, titulo)` — aviso fijo dentro de una pantalla |
| `diseno.html` | `encabezado_pagina(...)`, `estado_vacio(...)`, `insignia(...)`, `insignia_estado(...)`, `insignia_estado_cuenta(...)`, `dato(...)` |
| `destacados.html` | `icono_destacado(nombre, clase)` (como `icono()`, con algunos trazos extra), `rasgo(...)`, `cifra(...)`, `tarjeta_acceso(entrada, icono_nombre)` — los usan la bienvenida y el panel de inicio |
| `indicadores.html` | `tarjeta_indicador(etiqueta, valor, icono_nombre, tono, detalle, total, pendiente)` — cifra del panel de auditoría; con `total` muestra el porcentaje y una barra, y con `valor` en `none` muestra "sin datos" (nunca un 0); `tarjeta_grafico(id, titulo, descripcion, definicion, filas, vacio, resumen, centro, encabezados, exportacion)` — gráfico de Chart.js (ver ADR-010) con una tabla de los mismos datos para lectores de pantalla y para cuando no hay JavaScript (con `encabezados`, de N columnas) y, con `exportacion`, el menú de descarga; `menu_exportar(exportacion, titulo, grafico_id)` — descargas CSV y JSON de un indicador y, con `grafico_id`, la imagen PNG del gráfico; `encabezado_de_seccion(id, titulo, texto, apilada)` — con `{% call %}` los filtros van a la derecha (o debajo, con `apilada`); `filtro_segmentado(etiqueta, region, opciones)` — filtro propio de una sección; `encabezado_ordenable(texto, url, activo, direccion)` — columna que ordena la tabla con `aria-sort`; `aviso_de_error(titulo, mensaje, url_de_reintento)` — sección que no se pudo calcular, con reintento; `esqueleto_de_graficos(cantidad)` — lugar reservado mientras carga una región diferida; `insignia_gravedad(nivel)` — la gravedad de una emergencia como insignia de color. `valor` de `tarjeta_indicador` acepta un texto ya formateado ("5,0 días") |

`campo()` resuelve etiqueta, control, ayuda, errores de validación y accesibilidad. Un
`PasswordField` sale con el botón para mostrar u ocultar la contraseña; con `requisitos=true`
(contraseñas nuevas) muestra la política y la va marcando mientras se escribe.

```jinja
{% call tabla(["Nombre", "Estado", none]) %}
  {% for fila in filas %}
  <tr class="tabla-fila">
    {% call celda("Nombre") %}{{ fila.nombre }}{% endcall %}
    {% call celda("Estado") %}{{ insignia_estado(fila.activo) }}{% endcall %}
    {% call celda() %}<div class="tabla-acciones">…</div>{% endcall %}
  </tr>
  {% endfor %}
{% endcall %}
{{ paginacion(pagina) }}
```

### Tablas en el teléfono

Por debajo de `md` cada fila de `.tabla` se apila como una tarjeta y cada celda muestra su
etiqueta (`data-etiqueta`). Dos clases ajustan esa tarjeta: `.tabla-celda-principal` convierte la
celda que nombra la fila (una ONG, un rubro) en el título de la tarjeta, sin etiqueta, y
`.tabla-celda-escritorio` oculta en el teléfono lo que ese título ya dice (la posición del ranking).

### 2.3 Filtros y globales de Jinja (`backend/app/core/interfaz/plantillas.py`)

Filtros `etiqueta_rol`, `etiqueta_tipo_organizacion`, `etiqueta_estado_emergencia`,
`etiqueta_gravedad`, `etiqueta_tipo_necesidad` (el rubro de un ítem: "Personal sanitario"),
`descripcion_permiso`, `fecha` (`dd/mm/aaaa hh:mm`, hora de Argentina), `numero(decimales=0)`
(miles con punto y decimales con coma, redondeo "mitad hacia arriba": `12.500`, `5,0`) e
`id_corto` (los últimos 8 caracteres de un UUID, en mayúsculas: "Oferta #9F3A1C2B"; es solo para
leer, los enlaces y formularios usan el id completo); globales `requisitos_de_contrasena()` y
`url_de_pagina(n)`.

Las plantillas del panel de auditoría reciben además `exportacion(slug, imagen=None)`, que
devuelve las URLs de descarga CSV y JSON del indicador con el período y los filtros vigentes, y el
nombre del PNG del gráfico; `imagen` distingue ese nombre cuando dos gráficos comparten un
indicador (`app/modulos/indicadores/rutas.py`). El CSV empieza con el BOM de UTF-8 para que Excel
en Windows lea bien los acentos.

### 2.4 Comportamiento (`estaticos/js/interfaz.js`)

Lo carga `layout.html` en todas las pantallas. Los templates que ya traen su propio `<script>`
(navbar, login) lo siguen usando igual.

| Atributo | Efecto |
|---|---|
| `data-alerta-descartable` + `data-segundos` | El mensaje flash se cierra con su `[data-cerrar-alerta]` o solo al cumplirse el tiempo |
| `data-alternar-contrasena="id"` | Muestra u oculta la contraseña del campo |
| `data-requisitos-de="id"` | Marca los requisitos de la política que la contraseña va cumpliendo |
| `form[data-confirmar="texto"]` (+ `data-confirmar-titulo`, `data-confirmar-boton`) | Antes de enviar abre el modal de confirmación de la app (`<dialog>` con los estilos de `modal.css`), no el `confirm()` del navegador |
| `form[data-envio-con-carga]` | Al enviar deshabilita el `[data-boton-envio]` y muestra el spinner |
| `select[data-filtra-organizaciones]` + `data-campo-rol` | Muestra solo las organizaciones del tipo que exige el rol elegido |
| `body[data-minutos-sesion]` | Recarga la pantalla al vencer la sesión por inactividad |

Las pantallas con un comportamiento propio cargan su script al final de su bloque `content`:

| Script | Atributo | Efecto |
|---|---|---|
| `estaticos/js/indicadores.js` | `form[data-filtro-periodo]` + `data-mensaje-invertido` | Antes de enviar, avisa si la fecha "desde" es posterior a la "hasta" (el mismo mensaje que el servidor) y sincroniza los `min`/`max` de las dos fechas |
| `estaticos/js/indicadores.js` | `[data-filtro-de-seccion]` (sus enlaces) + `[data-panel-actualizable="nombre"]` | Aplica el filtro de la sección sin recargar: trae la pantalla del enlace, reemplaza solo las regiones actualizables, vuelve a dibujar los gráficos y cambia la URL. Si algo falla, sigue el enlace |
| `estaticos/js/graficos.js` (+ `vendor/chart-4.4.9.umd.js`) | `[data-grafico-contenedor]` con `script[data-grafico]` | Dibuja el gráfico de la definición JSON con los colores y la tipografía del sitio, y deja la tabla de respaldo solo para lectores de pantalla. Con `enlaces` en la definición, tocar una barra activa el enlace del filtro de la sección que lleva a esa URL (la sección "Convocatorias" lo usa para elegir la decisión del detalle). Expone `RescueSync.graficos.iniciar(raiz)` / `destruir(raiz)` |
| `estaticos/js/indicadores.js` | `[data-carga-diferida="url"]` + `data-mensaje-error`; `[data-reintentar]` | Completa la región con el fragmento HTML de esa URL apenas se muestra la pantalla (la sección "Proceso", que consulta Bonita) y vuelve a pedirlo con el botón de reintento. Si falla la red, muestra `data-mensaje-error` con un reintento |
| `estaticos/js/indicadores.js` | `details[data-exportar-menu]`; `[data-exportar-imagen="id del canvas"]` + `data-nombre-archivo` | Cierra el menú de exportación al hacer clic afuera, al elegir una descarga o con Escape. Muestra la opción de imagen (oculta sin JavaScript) y descarga el gráfico como PNG |
| `estaticos/js/indicadores.js` | `.panel-pestanas` | En pantallas angostas desplaza la barra de pestañas hasta centrar la activa, sin mover la página |

Nada de esto es seguridad: el servidor valida y autoriza todo por su cuenta.

## 3. Checklist para una pantalla nueva

1. **Ruta** en `backend/app/modulos/<modulo>/rutas.py`, con su `@requiere_permiso(...)`
   ([`autorizacion.md`](./autorizacion.md) sección 3).
2. **Respuesta según el cliente** (sección 5).
3. **Plantilla** que extiende `layout.html`.
4. **Entrada de menú**, si la pantalla tiene una tarjeta en el hub (sección 4).
5. **Tests** con las cabeceras de navegador de `tests/conftest.py` (`navegar`,
   `enviar_formulario`), además de los JSON.

## 4. Tarjetas del hub

Cada módulo declara su entrada con el mismo permiso que protege la ruta, y
`registrar_modulos()` la registra:

```python
ENTRADA_DE_MENU = EntradaDeMenu(
    endpoint="usuarios.listar",
    titulo="Usuarios",
    permiso=USUARIOS_LISTAR,
    icono="usuarios",
)
```

`hub.html` y `navbar.html` recorren `entradas_de_menu()` (ya filtrada por permisos): el hub dibuja una tarjeta por
entrada con `tarjeta_acceso()`. El ícono de cada tarjeta se elige por endpoint en el diccionario
`icono_por_endpoint` del propio `hub.html` (así cada sección tiene uno distinto); una entrada que
no figure ahí usa el `icono` que declaró, resuelto con `icono_destacado()` (carpeta si no existe).

## 5. Cómo responde una ruta (`backend/app/core/interfaz/vistas.py`)

La misma ruta atiende al navegador y a los clientes JSON; `pide_json()` decide según `Accept`
([`errores.md`](./errores.md) sección 2.1).

```python
@blueprint_usuarios.get("/<uuid:usuario_id>")
@requiere_permiso(USUARIOS_LISTAR)
def ver(usuario_id: uuid.UUID):
    datos = servicios.a_diccionario(servicios.obtener_usuario(usuario_id))
    if pide_json():
        return jsonify(datos)
    return render_template("usuarios/detalle.html", usuario=datos)


@blueprint_usuarios.post("/<uuid:usuario_id>/edicion")
@requiere_permiso(USUARIOS_EDITAR)
@plantilla_ante_error("usuarios/formulario.html", contexto=_contexto_del_formulario)
def editar(usuario_id: uuid.UUID):
    formulario = construir_formulario(FormularioEdicionDeUsuario)
    validar_o_fallar(formulario)
    usuario = servicios.editar_usuario(usuario_id, ...)
    return redirigir(
        "usuarios.ver",
        "Cambios guardados.",
        datos_json=servicios.a_diccionario(usuario),
        usuario_id=usuario.id,
    )
```

- **`redirigir(endpoint, mensaje, ...)`**: después de un POST exitoso, redirect con mensaje flash
  (Post/Redirect/Get) al navegador, JSON al resto.
- **`@plantilla_ante_error(plantilla, contexto, nombre_formulario)`**: si el formulario o el
  servicio fallan, el navegador vuelve a ver ese formulario con lo que cargó y cada error junto
  a su campo. Va **debajo** del decorador de autorización. La vista no escribe ningún `try`.
- **Pantallas de formulario**: un GET con función propia (`formulario_de_alta`,
  `formulario_de_edicion`) sobre la misma URL que el POST que las procesa.
- **Ids**: son UUID ([ADR-011](../adr/ADR-011-claves-uuid.md)). Las rutas los reciben con
  `<uuid:...>` (un id mal formado es 404); un campo de formulario que elige otra entidad es un
  `CampoId` (`app.core.interfaz.formularios`), que deja `data` como `uuid.UUID` y marca como error
  del campo lo que no sea un UUID; un id que llega suelto en un JSON se lee con `parsear_id()`
  (`app.core.identificadores`).
- **Listados**: siempre paginados en la base con `app.core.interfaz.paginacion`. El servicio arma la
  consulta con sus filtros y llama a `paginar()`; la ruta lee `?pagina=` y `?por_pagina=`
  (20 por defecto, 100 como tope) con `parametros_de_paginacion()`. El cliente JSON recibe
  los elementos y un objeto `paginacion` (`pagina`, `por_pagina`, `total`, `paginas`); la
  plantilla recibe la `Pagina` y la dibuja con `paginacion()`, que conserva los filtros.
