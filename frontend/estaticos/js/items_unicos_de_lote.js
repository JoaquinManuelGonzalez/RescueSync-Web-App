/*
 * Un item va una sola vez por lote de necesidad.
 *
 * Lo incluyen plantillas/lotes/formulario.html y plantillas/lotes/editar.html. En el
 * contenedor marcado con [data-items-unicos], las opciones ya elegidas en otra fila quedan
 * deshabilitadas, asi no se puede cargar dos veces el mismo item. Es solo una ayuda de la
 * interfaz: la regla la valida el backend (`_armar_lote_items` en lotes/servicios.py), que
 * rechaza el lote si llega un item repetido.
 *
 * Las filas las agrega y quita el script de cada pantalla; aca solo se observan.
 */
(() => {
  "use strict";

  function bloquearRepetidos(contenedor) {
    const selects = [...contenedor.querySelectorAll("select")];
    const elegidos = new Set(selects.map((select) => select.value).filter(Boolean));
    selects.forEach((select) => {
      [...select.options].forEach((opcion) => {
        opcion.disabled =
          opcion.value !== "" && opcion.value !== select.value && elegidos.has(opcion.value);
      });
    });
  }

  document.querySelectorAll("[data-items-unicos]").forEach((contenedor) => {
    contenedor.addEventListener("change", () => bloquearRepetidos(contenedor));
    new MutationObserver(() => bloquearRepetidos(contenedor)).observe(contenedor, {
      childList: true,
    });
    bloquearRepetidos(contenedor);
  });
})();
