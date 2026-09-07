import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Search, ShoppingCart, Sparkles, Wand2 } from "lucide-react";
import { getDemoCart } from "../api/products";
import { useCart } from "../context/CartContext";
import { useShelves } from "../hooks/useShelves";
import { PurchaseHistorySection } from "../components/history/PurchaseHistorySection";

// Los tres pasos del recorrido. La home antes era un título y 49 pills: no
// decía qué hacía la app ni por dónde empezar, y para alguien que abre el link
// sin que nadie se lo explique eso es toda la explicación que va a recibir.
const PASOS = [
  { Icon: Search, titulo: "Buscá productos", texto: "Los catálogos de Coto, Día y Carrefour, unificados por código de barras." },
  { Icon: ShoppingCart, titulo: "Armá tu changuito", texto: "Elegí lo que comprarías de verdad, con las cantidades que llevás." },
  { Icon: Sparkles, titulo: "Optimizamos el reparto", texto: "Calculamos en qué súper conviene comprar cada cosa, con envíos, promos y descuentos bancarios." },
];

export function HomePage() {
  // Las góndolas reales del catálogo, agrupadas igual que en el mega-menú.
  // Antes se aplanaban las 49 en una sola nube, que a esta altura es una pared
  // de pills sin jerarquía.
  const { sections } = useShelves();
  const { mergeItems } = useCart();
  const navigate = useNavigate();
  const [cargandoDemo, setCargandoDemo] = useState(false);

  // El atajo del arranque en frío. Es `mergeItems` y no `restoreItems` por la
  // misma razón que el "Repetir" del historial: la home puede visitarse con el
  // carrito lleno, y un botón que borra lo que había sería una trampa.
  async function probarCarritoDeEjemplo() {
    setCargandoDemo(true);
    try {
      const items = await getDemoCart();
      if (!items?.length) return;
      mergeItems(
        Object.fromEntries(
          items.map((item) => [item.unified_id, { name: item.name, quantity: item.quantity }])
        )
      );
      navigate("/carrito");
    } catch {
      // Falla en silencio y el usuario sigue armando el carrito a mano: es un
      // atajo, no un camino obligatorio.
    } finally {
      setCargandoDemo(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-10 sm:py-12">
      <div className="text-center">
        <h1 className="mb-3 font-display text-2xl font-bold text-brand-violet-700 sm:text-4xl">
          Comprá inteligente en Coto, Día y Carrefour
        </h1>
        <p className="mx-auto mb-8 max-w-xl text-ink-muted">
          Buscá productos, armá tu changuito y dejá que SmartCart encuentre la combinación de
          supermercados que menos te cuesta.
        </p>

        <button
          type="button"
          onClick={probarCarritoDeEjemplo}
          disabled={cargandoDemo}
          className="mx-auto mb-10 flex items-center gap-2 rounded-full bg-brand-accent px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-brand-accent-dark disabled:opacity-60"
        >
          <Wand2 size={18} aria-hidden="true" />
          {cargandoDemo ? "Armando el carrito…" : "Probar con un carrito de ejemplo"}
        </button>
      </div>

      <ol className="mb-12 grid grid-cols-1 gap-4 sm:grid-cols-3">
        {PASOS.map(({ Icon, titulo, texto }, indice) => (
          <li key={titulo} className="rounded-lg border border-line bg-surface p-4">
            <p className="mb-2 flex items-center gap-2 font-display text-sm font-bold text-brand-violet-700">
              <Icon size={18} aria-hidden="true" />
              {indice + 1}. {titulo}
            </p>
            <p className="text-sm text-ink-muted">{texto}</p>
          </li>
        ))}
      </ol>

      {sections.map((section) => (
        <div key={section.section} className="mb-8">
          <p className="mb-3 font-display text-sm font-semibold text-brand-accent">
            {section.section.toUpperCase()}
          </p>
          <div className="flex flex-wrap gap-2">
            {section.shelves.map((shelf) => (
              <Link
                key={shelf.slug}
                to={`/categoria/${shelf.slug}`}
                className="rounded-full border border-brand-violet-700 px-3 py-1.5 text-sm font-medium text-brand-violet-700 hover:bg-brand-violet-100"
              >
                {shelf.label}
              </Link>
            ))}
          </div>
        </div>
      ))}

      {/* Sin historial no renderiza nada, así que para un usuario nuevo esto no
          existe. */}
      <PurchaseHistorySection className="mt-12 text-left" />
    </div>
  );
}
