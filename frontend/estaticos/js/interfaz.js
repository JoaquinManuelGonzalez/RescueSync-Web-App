/* Comportamiento de la interfaz de RescueSync.
 *
 * JavaScript vanilla (ADR-001), activado por data-attributes. Lo carga layout.html en todas
 * las pantallas; las que ya traen su propio <script> (navbar, login) lo siguen usando. Cada
 * comportamiento es un bloque independiente:
 *
 *   [data-alerta-descartable]          mensaje flash que se cierra con su cruz o solo, a los N segundos
 *   [data-alternar-contrasena]         muestra u oculta la contraseña de su campo
 *   [data-requisitos-de]               marca los requisitos que la contraseña va cumpliendo
 *   form[data-confirmar]               pide confirmacion en un modal propio antes de enviar
 *   form[data-envio-con-carga]         deshabilita el boton y muestra el spinner al enviar
 *   select[data-filtra-organizaciones] filtra las organizaciones segun el rol elegido
 *   body[data-minutos-sesion]          recarga al vencer la sesion por inactividad
 *
 * Nada de esto es seguridad: el servidor valida y autoriza todo por su cuenta.
 */
(() => {
  "use strict";

  // --- Mensajes flash -------------------------------------------------------------

  // Los mensajes flash de layout.html se cierran con su cruz o solos a los `data-segundos`.
  // Con el mouse encima (o el foco adentro) la cuenta se detiene, para poder terminar de leer.
  function iniciarAlertasDescartables() {
    document.querySelectorAll("[data-alerta-descartable]").forEach((alerta) => {
      let temporizador = null;

      const eliminar = () => {
        const contenedor = alerta.parentElement;
        alerta.remove();
        // Sin mensajes, el contenedor (con sus margenes) tambien se va.
        if (contenedor && !contenedor.querySelector("[data-alerta-descartable]")) {
          contenedor.remove();
        }
      };

      // Se usa la Web Animations API y no una clase: la animacion de entrada de flash.css
      // (`animate-fade-down`) deja fija la opacidad final y le ganaria a cualquier clase.
      const quitar = () => {
        window.clearTimeout(temporizador);
        const salida = alerta.animate(
          [
            { opacity: 1, transform: "translateY(0)" },
            { opacity: 0, transform: "translateY(-8px)" },
          ],
          { duration: 250, easing: "ease-in", fill: "forwards" },
        );
        salida.finished.then(eliminar, eliminar);
      };

      const programar = () => {
        const segundos = Number(alerta.dataset.segundos);
        if (segundos > 0) temporizador = window.setTimeout(quitar, segundos * 1000);
      };
      const pausar = () => window.clearTimeout(temporizador);

      alerta.querySelector("[data-cerrar-alerta]")?.addEventListener("click", quitar);
      alerta.addEventListener("mouseenter", pausar);
      alerta.addEventListener("mouseleave", programar);
      alerta.addEventListener("focusin", pausar);
      alerta.addEventListener("focusout", programar);
      programar();
    });
  }

  // --- Contraseñas ---------------------------------------------------------------

  function iniciarAlternadoDeContrasenas() {
    document.querySelectorAll("[data-alternar-contrasena]").forEach((boton) => {
      const campo = document.getElementById(boton.dataset.alternarContrasena);
      if (!campo) return;

      boton.addEventListener("click", () => {
        const mostrar = campo.type === "password";
        campo.type = mostrar ? "text" : "password";
        const texto = mostrar ? "Ocultar contraseña" : "Mostrar contraseña";
        boton.setAttribute("aria-pressed", String(mostrar));
        boton.setAttribute("aria-label", texto);
        boton.title = texto;
        boton.querySelector("[data-icono-mostrar]")?.classList.toggle("hidden", mostrar);
        boton.querySelector("[data-icono-ocultar]")?.classList.toggle("hidden", !mostrar);
      });

      // Al enviar vuelve a ocultarse, para que el navegador no la guarde como texto visible.
      campo.form?.addEventListener("submit", () => {
        campo.type = "password";
      });
    });
  }

  // Misma regla que app/core/seguridad.py: la validacion de verdad es la del servidor.
  const VERIFICADORES_DE_REQUISITO = {
    longitud: (valor, minimo) => [...valor].length >= minimo,
    mayuscula: (valor) => /\p{Lu}/u.test(valor),
    numero: (valor) => /\p{Nd}/u.test(valor),
    especial: (valor) => /[^\p{L}\p{N}\s]/u.test(valor),
  };

  function iniciarRequisitosDeContrasena() {
    document.querySelectorAll("[data-requisitos-de]").forEach((lista) => {
      const campo = document.getElementById(lista.dataset.requisitosDe);
      if (!campo) return;
      const minimo = Number(lista.dataset.longitudMinima) || 0;

      const actualizar = () => {
        lista.querySelectorAll("[data-requisito]").forEach((item) => {
          const verificar = VERIFICADORES_DE_REQUISITO[item.dataset.requisito];
          item.classList.toggle("requisito-cumplido", Boolean(verificar?.(campo.value, minimo)));
        });
      };

      campo.addEventListener("input", actualizar);
      actualizar();
    });
  }

  // --- Formularios ---------------------------------------------------------------

  // Modal de confirmacion propio (estilos en src/componentes/modal.css). Se arma una sola vez
  // sobre un <dialog> nativo. El texto de cada formulario se carga con textContent, nunca como
  // HTML.
  const ICONO_ADVERTENCIA =
    '<svg class="size-6" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"/></svg>';

  let dialogo = null;

  function obtenerDialogo() {
    if (dialogo) return dialogo;
    dialogo = document.createElement("dialog");
    dialogo.className = "modal";
    dialogo.setAttribute("aria-labelledby", "modal-confirmacion-titulo");
    dialogo.setAttribute("aria-describedby", "modal-confirmacion-texto");
    dialogo.innerHTML = `
      <div class="modal-panel">
        <div class="modal-encabezado">
          <span class="modal-icono">${ICONO_ADVERTENCIA}</span>
          <div>
            <h2 id="modal-confirmacion-titulo" class="modal-titulo"></h2>
            <p id="modal-confirmacion-texto" class="modal-texto"></p>
          </div>
        </div>
        <div class="modal-acciones">
          <button type="button" class="btn btn-secundario" data-modal-cancelar>Cancelar</button>
          <button type="button" class="btn btn-primario" data-modal-aceptar></button>
        </div>
      </div>`;
    document.body.append(dialogo);

    dialogo.querySelector("[data-modal-cancelar]").addEventListener("click", () => {
      dialogo.close("cancelar");
    });
    dialogo.querySelector("[data-modal-aceptar]").addEventListener("click", () => {
      dialogo.close("aceptar");
    });
    // Un clic en el fondo oscuro (fuera del panel) cancela, igual que Esc.
    dialogo.addEventListener("click", (evento) => {
      if (evento.target === dialogo) dialogo.close("cancelar");
    });
    return dialogo;
  }

  function pedirConfirmacion({ titulo, texto, boton }) {
    const modal = obtenerDialogo();
    modal.querySelector(".modal-titulo").textContent = titulo;
    modal.querySelector(".modal-texto").textContent = texto;
    modal.querySelector("[data-modal-aceptar]").textContent = boton;
    modal.returnValue = "";
    modal.showModal();
    // El foco arranca en "Cancelar": confirmar una accion destructiva exige un paso deliberado.
    modal.querySelector("[data-modal-cancelar]").focus();
    return new Promise((resolver) => {
      modal.addEventListener("close", () => resolver(modal.returnValue === "aceptar"), {
        once: true,
      });
    });
  }

  // Se registra antes que el envio con carga: el primer submit se cancela para abrir el modal,
  // y el otro manejador lo ve cancelado y no deshabilita el boton. Si se confirma, se vuelve a
  // enviar el formulario ya marcado como confirmado.
  function iniciarConfirmaciones() {
    if (typeof HTMLDialogElement !== "function") {
      // Navegador sin <dialog>: queda el confirm() nativo antes que no confirmar.
      document.querySelectorAll("form[data-confirmar]").forEach((formulario) => {
        formulario.addEventListener("submit", (evento) => {
          if (!window.confirm(formulario.dataset.confirmar)) evento.preventDefault();
        });
      });
      return;
    }

    document.querySelectorAll("form[data-confirmar]").forEach((formulario) => {
      formulario.addEventListener("submit", async (evento) => {
        if (formulario.dataset.confirmado === "si") return;
        evento.preventDefault();

        const confirmado = await pedirConfirmacion({
          titulo: formulario.dataset.confirmarTitulo || "¿Confirmás esta acción?",
          texto: formulario.dataset.confirmar,
          boton: formulario.dataset.confirmarBoton || "Confirmar",
        });
        if (!confirmado) return;

        formulario.dataset.confirmado = "si";
        if (formulario.requestSubmit) formulario.requestSubmit();
        else formulario.submit();
      });
    });

    // Si se vuelve con "atras", el formulario tiene que volver a pedir confirmacion.
    window.addEventListener("pageshow", () => {
      document.querySelectorAll("form[data-confirmado]").forEach((formulario) => {
        delete formulario.dataset.confirmado;
      });
    });
  }

  function iniciarEnviosConCarga() {
    document.querySelectorAll("form[data-envio-con-carga]").forEach((formulario) => {
      formulario.addEventListener("submit", (evento) => {
        if (evento.defaultPrevented) return;
        const boton = formulario.querySelector("[data-boton-envio]");
        if (!boton) return;

        boton.disabled = true;
        boton.querySelector("[data-spinner]")?.classList.remove("hidden");
        const texto = boton.querySelector("[data-texto]");
        if (texto && boton.dataset.textoCargando) {
          texto.dataset.textoOriginal = texto.textContent;
          texto.textContent = boton.dataset.textoCargando;
        }
      });
    });

    // Al volver con "atras", el navegador puede restaurar la pagina con el boton deshabilitado.
    window.addEventListener("pageshow", (evento) => {
      if (!evento.persisted) return;
      document.querySelectorAll("[data-boton-envio]").forEach((boton) => {
        boton.disabled = false;
        boton.querySelector("[data-spinner]")?.classList.add("hidden");
        const texto = boton.querySelector("[data-texto]");
        if (texto?.dataset.textoOriginal) texto.textContent = texto.dataset.textoOriginal;
      });
    });
  }

  // Alta y edicion de cuentas: muestra solo las organizaciones del tipo que exige el rol.
  // Es comodidad; la coherencia la valida el servidor.
  function iniciarFiltroDeOrganizaciones() {
    document.querySelectorAll("select[data-filtra-organizaciones]").forEach((select) => {
      const selectDeRol = document.getElementById(select.dataset.campoRol);
      if (!selectDeRol) return;

      let tipoPorRol;
      try {
        tipoPorRol = JSON.parse(select.dataset.filtraOrganizaciones);
      } catch {
        return;
      }

      const aplicar = () => {
        const tipo = tipoPorRol[selectDeRol.value] ?? null;
        for (const opcion of select.options) {
          // La opcion vacia ("Sin organizacion") solo tiene sentido si el rol no lleva una.
          const oculta = opcion.value === "" ? tipo !== null : opcion.dataset.tipo !== tipo;
          opcion.hidden = oculta;
          opcion.disabled = oculta;
        }
        if (select.selectedOptions[0]?.hidden) {
          const primeraVisible = Array.from(select.options).find((opcion) => !opcion.hidden);
          select.value = primeraVisible ? primeraVisible.value : "";
        }
      };

      selectDeRol.addEventListener("change", aplicar);
      aplicar();
    });
  }

  // --- Sesion --------------------------------------------------------------------

  // La sesion vence en el servidor a los N minutos sin actividad. Si la pantalla queda
  // abierta ese tiempo, se recarga para que la persona vea el aviso de sesion vencida en vez
  // de descubrirlo al enviar un formulario.
  function iniciarAvisoDeInactividad() {
    const minutos = Number(document.body.dataset.minutosSesion);
    if (!minutos) return;
    window.setTimeout(() => window.location.reload(), (minutos * 60 + 5) * 1000);
  }

  document.addEventListener("DOMContentLoaded", () => {
    iniciarAlertasDescartables();
    iniciarAlternadoDeContrasenas();
    iniciarRequisitosDeContrasena();
    iniciarConfirmaciones();
    iniciarEnviosConCarga();
    iniciarFiltroDeOrganizaciones();
    iniciarAvisoDeInactividad();
  });
})();
