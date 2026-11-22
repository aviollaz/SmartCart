import { ChevronDown } from "lucide-react";
import { FeedbackBanner } from "../components/common/FeedbackBanner";
import { STORE_NAMES_LIST } from "../utils/formatters";

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
        a: `Te dice cuánto sale tu carrito entero en cada súper: ${STORE_NAMES_LIST}. Vos lo armás una sola vez y SmartCart lo cotiza en todos, con envío, promos y tus descuentos bancarios. Si dividir la compra entre dos súper te ahorra bastante, también te lo ofrece.`,
      },
      {
        q: "¿Cómo calcula el precio en cada súper?",
        a: "Para cada producto toma el precio real con la cantidad que llevás, aplicando las promos (2x1, segunda unidad al 50%, etc.) y las de las membresías que declaraste. Después suma el envío a tu dirección y descuenta el mejor descuento bancario de tus tarjetas en ese súper, con su tope.",
      },
      {
        q: "¿Qué pasa si un súper no tiene un producto?",
        a: "Lo reemplazamos por el más parecido que sí tiene: mismo tipo de producto y tamaño equivalente. Abriendo la fila del súper podés elegir otro reemplazo o ninguno. Lo que queda sin reemplazo se cuenta al precio del súper más caro que lo tiene, porque lo vas a tener que comprar en otro lado: así un súper no parece más barato sólo por tener menos cosas.",
      },
      {
        q: "¿Qué es «Otro día»?",
        a: "Los descuentos bancarios cambian según el día de la semana. «Otro día» es lo que te saldría el mismo carrito en ese súper el día más barato de la próxima semana, pagando con tu tarjeta. Si ningún día es más barato que hoy, dice «sin promo».",
      },
      {
        q: "¿Cuándo me conviene dividir la compra?",
        a: "Debajo de la comparación aparece un aviso sólo cuando repartir el carrito entre varios súper ahorra bastante frente al más barato que tiene todo. Cada súper extra es otro envío, otro mínimo de compra y otro pago, así que una diferencia chica no vale la pena. Con «Ver cómo dividir» ves qué comprar en cada uno, y ahí podés limitar a cuántos súper querés ir.",
      },
      {
        q: "¿Por qué el total no coincide con el subtotal estimado?",
        a: "El subtotal estimado es la suma de los precios que ves, por unidad y sin envíos. Al comparar, cada total suma el envío y aplica las promos por cantidad y tus descuentos bancarios. Por eso puede salir más alto o más bajo que el estimado.",
      },
      {
        q: "¿Qué supermercados y zonas cubre?",
        a: `${STORE_NAMES_LIST}, con envío a domicilio en CABA y el Gran Buenos Aires. Si un súper nos dice que no entrega en tu dirección, lo sacamos de la comparación.`,
      },
    ],
  },
  {
    grupo: "Armar el carrito",
    preguntas: [
      {
        q: "¿Cómo agrego productos?",
        a: "Buscándolos en la barra de arriba, tocando una sección (Almacén, Bebidas…) de la fila de abajo del buscador, o repitiendo una compra anterior.",
      },
      {
        q: "¿Cómo compro frutas, verduras y carne?",
        a: "Los que se venden por peso van por kilo: cada unidad que agregás al carrito es 1 kg. Los que se venden por pieza (un mango, un atado de rúcula) van por unidad.",
      },
      {
        q: "¿Por qué no aparecen productos de un súper?",
        a: "Puede ser que ese súper no entregue en tu dirección (la cambiás desde «Envío a…», arriba de todo), que lo hayas desmarcado en el botón de supermercados de arriba o en «Supermercados», en el carrito, o simplemente que no venda ese producto.",
      },
    ],
  },
  {
    grupo: "Comprar y pagar",
    preguntas: [
      {
        q: "¿Compro en SmartCart?",
        a: "No. SmartCart no vende nada ni cobra. Abriendo la fila de un súper, el botón «Comprar en…» te lleva a su sitio: en Día, Carrefour, Vea, ChangoMás y Jumbo con el carrito ya cargado, y en Coto con una lista de los productos para agregarlos. Pagás ahí, como siempre, y SmartCart nunca ve tus datos de pago.",
      },
      {
        q: "¿Cómo uso mis descuentos bancarios?",
        a: "Marcá tus tarjetas y billeteras en «Medios de pago», en el carrito. SmartCart las tiene en cuenta en el precio de cada súper; después tenés que pagar con esa tarjeta en el sitio del súper para que el descuento se aplique.",
      },
      {
        q: "¿Puedo dejar afuera un supermercado?",
        a: "Sí. Desmarcalo en el botón de supermercados, arriba de todo, o en «Supermercados», en el carrito: deja de aparecer en los precios y en la comparación.",
      },
      {
        q: "¿Y las membresías (Comunidad Coto, Mi Carrefour…)?",
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

      <FeedbackBanner className="mt-10" />
    </div>
  );
}
