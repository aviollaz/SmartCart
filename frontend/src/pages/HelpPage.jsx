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
        a: "Compara los precios de Coto, Día, Carrefour y Vea y reparte tu compra entre ellos para que pagues lo menos posible. Vos armás el carrito una sola vez; SmartCart te dice qué conviene comprar en cada súper.",
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
        q: "¿Qué significa «Ahorrás $X»?",
        a: "Es la diferencia, producto por producto, entre lo que cuesta en promedio en los otros súper que lo tienen y el que te recomendamos. No incluye envíos ni descuentos bancarios, así que no es la resta de dos totales. En «Ver de dónde sale» está el detalle. Si todos tus productos están en un solo súper, no hay contra qué comparar y no se muestra.",
      },
      {
        q: "¿Qué es «Podés ahorrar hasta $X más»?",
        a: "Son opciones que cambian el resultado, cada una con su efecto en el total: reemplazar un producto por uno equivalente más barato del mismo pasillo, dejar afuera un súper entero cambiando los pocos productos que sólo tiene él, o comprar en menos súper pagando un poco más. Ninguna se aplica sola: elegís vos y SmartCart vuelve a optimizar.",
      },
      {
        q: "¿Qué supermercados y zonas cubre?",
        a: "Coto, Día, Carrefour y Vea, con envío a domicilio. Al cargar tu dirección consultamos a cada cadena si entrega ahí; las que no llegan quedan afuera de la comparación y te avisamos. Vea viene deshabilitado (ver más abajo).",
      },
      {
        q: "¿Están todos los productos de cada súper?",
        a: "No: comparamos una selección de góndolas que las cuatro cadenas tienen en común (almacén, frescos, frutas y verduras, carnes, desayuno, bebidas, congelados, limpieza y perfumería). Quedan afuera, por ejemplo, medicamentos, maquillaje, perfumes, pañales, pescadería y panadería. Lo que más se compara son los productos de marca, porque son los que se pueden identificar como el mismo producto en las distintas cadenas.",
      },
    ],
  },
  {
    grupo: "Armar el carrito",
    preguntas: [
      {
        q: "¿Cómo agrego productos?",
        a: "Buscándolos en la barra de arriba, navegando las categorías, desde los descuentos de la página principal o repitiendo una compra anterior. Si querés ver cómo funciona sin armar nada, usá «Probar con un carrito de ejemplo» en la página principal.",
      },
      {
        q: "¿Por qué no aparecen productos de un súper?",
        a: "Por una de tres razones, y la página te dice cuál: no entrega en la dirección que cargaste (la podés cambiar desde «Envío a…», arriba de todo), lo deshabilitaste en el carrito, en «Supermercados», o es Vea, que viene deshabilitado por seguridad.",
      },
      {
        q: "¿Por qué Vea viene deshabilitado?",
        a: "Porque en octubre de 2026 encontramos en vea.com.ar código malicioso que intenta robar datos de tarjeta. Sigue en el catálogo, pero no lo usamos hasta que lo habilites a mano en «Supermercados», en el carrito. Si lo habilitás, revisá que el pago se haga en la página oficial de Vea.",
      },
      {
        q: "¿Puedo dejar afuera un súper o comprar en menos súper?",
        a: "Sí. En el carrito, en «Supermercados», podés desmarcar los que no quieras usar y elegir «Comprar en como máximo» uno o más súper. Cada súper del reparto es una compra aparte que hacés a mano, así que a veces vale la pena pagar un poco más por hacer menos compras: al optimizar te mostramos cuánto cuesta.",
      },
      {
        q: "¿Qué es «Compro» en el carrito?",
        a: "Hasta cuándo podés esperar para comprar. Los descuentos bancarios cambian según el día de la semana, así que si no necesitás comprar hoy, SmartCart elige el mejor día para cada súper dentro del plazo y te lo indica en cada uno. Si comprar todo hoy sale igual o más barato, te recomienda hoy.",
      },
      {
        q: "¿Por qué el total al optimizar es mayor que el del carrito?",
        a: "El monto del carrito es una estimación: la suma del precio más barato de cada producto, sin envío. Al optimizar se suman los envíos y, para llegar al mínimo de compra de un súper, a veces conviene mover un producto a uno un poco más caro. Por eso el total final puede ser algo mayor.",
      },
    ],
  },
  {
    grupo: "Comprar y pagar",
    preguntas: [
      {
        q: "¿Compro en SmartCart?",
        a: "No. SmartCart no vende nada ni cobra. Al optimizar, el botón «Comprar en…» te lleva al sitio de cada súper con el carrito ya cargado. Coto no permite cargar un carrito desde afuera, así que para Coto te mostramos la lista de productos con un link a cada uno para que los agregues. Pagás en el sitio del súper, como siempre, y SmartCart nunca ve tus datos de pago.",
      },
      {
        q: "¿Cómo uso mis descuentos bancarios?",
        a: "Marcá tus tarjetas y billeteras en «Medios de pago», en el carrito. SmartCart las tiene en cuenta para elegir el reparto, según el día en que vas a comprar; después tenés que pagar con esa tarjeta, ese día, en el sitio del súper para que el descuento se aplique.",
      },
      {
        q: "¿Y las membresías (Club Día, Mi Carrefour, Comunidad Coto…)?",
        a: "Si declarás una, los precios que ves ya incluyen sus descuentos. Para que el súper te los respete, tenés que estar logueado como socio al pagar. Las podés cambiar desde «Mis clubes», arriba de todo en cualquier página, o en «Medios de pago» del carrito.",
      },
      {
        q: "¿Cómo se calcula el envío?",
        a: "Con tu dirección le consultamos a cada cadena su costo de envío. En Día depende del peso del carrito, así que lo cotizamos con tus productos reales. Si un súper no responde, usamos el costo habitual de tu zona y lo marcamos como «Envío (estimado)».",
      },
    ],
  },
  {
    grupo: "Precios y datos",
    preguntas: [
      {
        q: "¿Los precios están actualizados?",
        a: "Se relevan todas las noches de los sitios de cada súper. Durante el día pueden cambiar, así que el precio final lo confirma el súper cuando cerrás la compra.",
      },
      {
        q: "¿Por qué el súper me dice que no hay stock de algo que SmartCart mostraba?",
        a: "Porque el stock que publican las cadenas es general, no el de la sucursal que te entrega. Un producto puede figurar disponible y que el súper te avise al pagar que no lo tiene para tu dirección.",
      },
      {
        q: "¿De dónde salen las descripciones de los productos?",
        a: "Del sitio de cada súper, y por eso dicen de cuál («Según Día»). Es el texto que publica la cadena, no algo que SmartCart verificó.",
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
