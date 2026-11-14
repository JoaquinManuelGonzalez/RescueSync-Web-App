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
 *   [data-temporizador-convocatoria] muestra el tiempo restante de una convocatoria abierta
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

  // Misma regla que app/core/acceso/seguridad.py: la validacion de verdad es la del servidor.
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

  // La habilitacion visual no reemplaza la validacion del servidor: solo evita envios
  // incompletos mientras se seleccionan las lineas.
  function iniciarSeleccionDeOfertas() {
    document.querySelectorAll("form[data-seleccion-ofertas]").forEach((formulario) => {
      const lineas = [...formulario.querySelectorAll("[data-linea-seleccionable]")];
      const boton = formulario.querySelector("[data-confirmar-seleccion]");
      const mensaje = formulario.querySelector("[data-mensaje-seleccion]");
      if (!boton) return;

      const actualizar = () => {
        const cantidades = new Map();
        lineas.forEach((linea) => {
          if (!linea.checked) return;
          const itemId = linea.dataset.loteItemId;
          cantidades.set(
            itemId,
            (cantidades.get(itemId) || 0) + Number(linea.dataset.cantidadOfrecida),
          );
        });

        let cumple = true;
        formulario.querySelectorAll("[data-requisito-item]").forEach((requisito) => {
          const requerida = Number(requisito.dataset.cantidadRequerida);
          const seleccionada = cantidades.get(requisito.dataset.requisitoItem) || 0;
          const valido = seleccionada * 4 >= requerida * 3 && seleccionada * 4 <= requerida * 5;
          cumple = cumple && valido;

          const estado = requisito.querySelector("[data-estado-requisito]");
          if (estado) {
            estado.textContent = `${seleccionada} / ${requerida} (75% mínimo · 125% máximo)`;
            estado.classList.toggle("text-green-700", valido);
            estado.classList.toggle("text-red-700", !valido);
          }
        });

        boton.disabled = !cumple;
        boton.setAttribute("aria-disabled", String(!cumple));
        if (mensaje) mensaje.hidden = cumple;
      };

      lineas.forEach((linea) => linea.addEventListener("change", actualizar));
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
          <button type="button" class="btn btn-cancelar" data-modal-cancelar>Cancelar</button>
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

  function iniciarBusquedasAutomaticas() {
    document.querySelectorAll("form[data-busqueda-automatica]").forEach((formulario) => {
      let temporizador = null;
      const campoTexto = formulario.querySelector('input[name="texto"]');

      const enviar = () => formulario.requestSubmit ? formulario.requestSubmit() : formulario.submit();

      formulario.querySelectorAll("select").forEach((select) => {
        select.addEventListener("change", enviar);
      });

      campoTexto?.addEventListener("input", () => {
        window.clearTimeout(temporizador);
        temporizador = window.setTimeout(enviar, 300);
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

  // El servidor sigue siendo la fuente de verdad del estado y del vencimiento. Este contador
  // solo comunica el tiempo restante con la hora del navegador y no altera la convocatoria.
  function iniciarTemporizadoresDeConvocatoria() {
    document.querySelectorAll("[data-temporizador-convocatoria]").forEach((temporizador) => {
      const salida = temporizador.querySelector("[data-tiempo-restante]");
      const cierre = Date.parse(temporizador.dataset.fechaCierre);
      if (!salida || Number.isNaN(cierre)) return;

      const actualizar = () => {
        const restante = cierre - Date.now();
        if (restante <= 0) {
          salida.textContent = "Convocatoria vencida";
          salida.classList.remove("text-primario");
          salida.classList.add("text-red-600");
          return false;
        }

        const totalSegundos = Math.floor(restante / 1000);
        const dias = Math.floor(totalSegundos / 86400);
        const horas = Math.floor((totalSegundos % 86400) / 3600);
        const minutos = Math.floor((totalSegundos % 3600) / 60);
        const segundos = totalSegundos % 60;
        const partes = [];
        if (dias) partes.push(`${dias}d`);
        partes.push(`${String(horas).padStart(2, "0")}h`);
        partes.push(`${String(minutos).padStart(2, "0")}m`);
        partes.push(`${String(segundos).padStart(2, "0")}s`);
        salida.textContent = partes.join(" ");
        return true;
      };

      actualizar();
      const intervalo = window.setInterval(() => {
        if (!actualizar()) window.clearInterval(intervalo);
      }, 1000);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    iniciarAlertasDescartables();
    iniciarAlternadoDeContrasenas();
    iniciarRequisitosDeContrasena();
    iniciarSeleccionDeOfertas();
    iniciarConfirmaciones();
    iniciarEnviosConCarga();
    iniciarBusquedasAutomaticas();
    iniciarFiltroDeOrganizaciones();
    iniciarTemporizadoresDeConvocatoria();
    iniciarAvisoDeInactividad();
  });
})();
