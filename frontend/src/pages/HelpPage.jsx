import { ChevronDown, MessageSquare } from "lucide-react";
import { FEEDBACK_FORM_URL } from "../utils/constants";

/**
 * Preguntas frecuentes. El contenido es texto estático y vive acá: no hay
 * lógica que duplicar, sólo explicar lo que la app ya hace.
 *
 * Regla para editarlo: nada de números que viven en otro lado (mínimos de
 * compra, costos de envío, porcentajes). Esos cambian en el backend o en
 * deliveryCosts.js sin que nadie se acuerde de esta página, y una FAQ que
 * contradice a la app es peor que una que no dice el número.
 */
const FAQ = [
  {
    grupo: "Cómo funciona",
    preguntas: [
      {
        q: "¿Qué hace SmartCart?",
        a: "Compara los precios de Coto, Día y Carrefour y reparte tu compra entre ellos para que pagues lo menos posible. Vos armás el carrito una sola vez; SmartCart te dice qué conviene comprar en cada súper.",
      },
      {
        q: "¿Cómo decide dónde comprar cada cosa?",
        a: "Para cada producto calcula el precio real en cada súper con la cantidad que llevás, aplicando las promos (2x1, segunda unidad al 50%, etc.) y las de las membresías que declaraste. Después suma lo que cambia al repartir: el envío de cada súper, su mínimo de compra y los descuentos bancarios de tus tarjetas, que tienen tope. Con todo eso busca la combinación más barata posible, no una aproximación.",
      },
      {
        q: "¿Por qué a veces me recomienda comprar todo en un solo súper?",
        a: "Porque cada súper suma su propio envío y tiene un mínimo de compra. Si lo que ahorrás repartiendo no alcanza a cubrir un segundo envío, o no llegás al mínimo de otra cadena, lo más barato es comprar todo junto.",
      },
      {
        q: "¿Qué significa «Ahorrás $X usando el sitio»?",
        a: "Es la diferencia, producto por producto, entre el súper más caro que lo tiene y el que te recomendamos. No incluye envíos ni descuentos bancarios, así que no es la resta de dos totales. En «Ver de dónde sale» está el detalle.",
      },
      {
        q: "¿Qué supermercados y zonas cubre?",
        a: "Coto, Día y Carrefour, con envío a domicilio en CABA y el Gran Buenos Aires. Si Coto no entrega en tu dirección, lo sacamos de la comparación y te avisamos.",
      },
    ],
  },
  {
    grupo: "Armar el carrito",
    preguntas: [
      {
        q: "¿Cómo agrego productos?",
        a: "Buscándolos en la barra de arriba, navegando las categorías, o repitiendo una compra anterior. Si querés ver cómo funciona sin armar nada, usá «Probar con un carrito de ejemplo» en la página principal.",
      },
      {
        q: "¿Por qué no aparecen productos de Coto?",
        a: "Porque Coto no entrega en la dirección que cargaste. Podés cambiarla desde «Envío a…», arriba de todo.",
      },
    ],
  },
  {
    grupo: "Comprar y pagar",
    preguntas: [
      {
        q: "¿Compro en SmartCart?",
        a: "No. SmartCart no vende nada ni cobra. Al optimizar, el botón «Comprar en…» te lleva al sitio de cada súper: en Día y Carrefour con el carrito ya cargado, y en Coto con los productos abiertos para agregarlos. Pagás ahí, como siempre, y SmartCart nunca ve tus datos de pago.",
      },
      {
        q: "¿Cómo uso mis descuentos bancarios?",
        a: "Marcá tus tarjetas y billeteras en «Medios de pago», en el carrito. SmartCart las tiene en cuenta para elegir el reparto; después tenés que pagar con esa tarjeta en el sitio del súper para que el descuento se aplique.",
      },
      {
        q: "¿Y las membresías (Club Día, Mi Carrefour…)?",
        a: "Si declarás una, los precios que ves ya incluyen sus descuentos. Para que el súper te los respete, tenés que estar logueado como socio al pagar. Las podés cambiar desde «Mis clubes», arriba de todo en cualquier página, o en «Medios de pago» del carrito.",
      },
    ],
  },
  {
    grupo: "Precios y datos",
    preguntas: [
      {
        q: "¿Los precios están actualizados?",
        a: "Se relevan todas las noches de los sitios de cada súper. Durante el día pueden cambiar, así que el precio y el stock finales los confirma el súper cuando cerrás la compra.",
      },
      {
        q: "¿Dónde se guardan mis datos?",
        a: "En tu navegador. No hay cuentas ni contraseñas: tu dirección, tu carrito y tu historial quedan en este dispositivo. Si borrás los datos del sitio, se borran también.",
      },
    ],
  },
];

export function HelpPage() {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8">
      <h1 className="mb-2 font-display text-2xl font-bold text-ink">Preguntas frecuentes</h1>
      <p className="mb-8 text-sm text-ink-muted">Cómo funciona SmartCart, cómo armar tu carrito y cómo comprar.</p>

      <div className="flex flex-col gap-8">
        {FAQ.map(({ grupo, preguntas }) => (
          <section key={grupo}>
            <h2 className="mb-3 font-display text-lg font-bold text-brand-violet-700">{grupo}</h2>
            <div className="divide-y divide-line rounded-lg border border-line bg-surface">
              {preguntas.map(({ q, a }) => (
                <details key={q} className="group">
                  <summary className="flex cursor-pointer select-none items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-ink">
                    {q}
                    <ChevronDown
                      size={16}
                      className="shrink-0 text-ink-muted transition-transform group-open:rotate-180"
                    />
                  </summary>
                  <p className="px-4 pb-4 text-sm leading-relaxed text-ink-muted">{a}</p>
                </details>
              ))}
            </div>
          </section>
        ))}
      </div>

      {FEEDBACK_FORM_URL && (
        <div className="mt-10 flex flex-wrap items-center justify-between gap-4 rounded-lg border border-brand-violet-100 bg-brand-violet-100 p-5">
          <p className="flex items-center gap-2 text-sm text-ink">
            <MessageSquare size={18} className="shrink-0 text-brand-violet-700" aria-hidden="true" />
            ¿Algo no anda o tenés una idea? Nos ayuda mucho saberlo.
          </p>
          <a
            href={FEEDBACK_FORM_URL}
            target="_blank"
            rel="noreferrer"
            className="rounded-md bg-brand-accent px-4 py-2 text-sm font-semibold text-white hover:bg-brand-accent-dark"
          >
            Contanos
          </a>
        </div>
      )}
    </div>
  );
}
