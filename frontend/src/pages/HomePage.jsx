import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Tag } from "lucide-react";
import { getDeals } from "../api/products";
import { useShelves } from "../hooks/useShelves";
import { useProfile } from "../context/ProfileContext";
import { STORE_NAMES_LIST } from "../utils/formatters";
import { stripUnavailableStores } from "../utils/storeAvailability";
import { ProductCarousel } from "../components/plp/ProductCarousel";
import { PurchaseHistorySection } from "../components/history/PurchaseHistorySection";

// Cuántas ofertas trae la home. Van en un carrusel de una sola fila, así que
// traer más no ocupa más pantalla: sólo alarga lo que se puede recorrer con
// las flechas. El backend topea en DEALS_MAX_LIMIT (src/api.py).
const DEALS_LIMIT = 50;

export function HomePage() {
  // Ya no hay botón de "carrito de ejemplo": era lo más llamativo de la home,
  // los usuarios lo tocaban sin leer (varias veces, sumando cantidades) y
  // después no sabían cómo vaciarlo. Para empezar está la barra de secciones
  // del header; el video muestra el recorrido sin tocar el carrito de nadie.
  // Tampoco hay "Ir a mi carrito": duplicaba el botón del header, que es el
  // que se destaca.
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:py-12">
      <section className="text-center">
        <h1 className="mb-3 font-display text-3xl font-bold text-brand-violet-700 sm:text-4xl">
          Tu changuito, al menor precio
        </h1>
        <p className="mx-auto max-w-3xl text-balance text-lg text-ink/80">
          Comparamos {STORE_NAMES_LIST} y armamos tu lista de compras al mejor precio.
        </p>
      </section>

      <HowItWorks />
      <DealsSection />

      {/* Sin historial no renderiza nada, así que para un usuario nuevo esto no
          existe. */}
      <PurchaseHistorySection className="mt-12 text-left" />
    </div>
  );
}

// El recorrido grabado en la app real: agregar productos → optimizar → dónde
// comprar cada cosa. Mudo, en loop y sin controles, se ve como un GIF pero pesa
// una fracción. Grabado aparte (frontend/public/como-funciona.mp4): si la UI
// cambia mucho, hay que regrabarlo.
function HowItWorks() {
  return (
    <section aria-label="Cómo funciona" className="mt-12">
      <p className="mb-3 text-center font-display text-base font-bold text-ink">Así funciona</p>
      <video
        src="/como-funciona.mp4"
        autoPlay
        muted
        loop
        playsInline
        className="mx-auto w-full max-w-3xl rounded-xl border border-line"
      />
      <p className="mt-4 text-center text-sm">
        <Link to="/ayuda" className="font-semibold text-brand-violet-700 hover:underline">
          ¿Dudas? Mirá las preguntas frecuentes
        </Link>
      </p>
    </section>
  );
}

function DealsSection() {
  const { memberships, hiddenStores } = useProfile();
  const { sections } = useShelves();
  const membershipsKey = (memberships || []).join(",");
  // "" = todas las secciones. Estado local y sin persistir: es una forma de
  // mirar la home, no una preferencia del usuario.
  const [section, setSection] = useState("");
  const [state, setState] = useState({ deals: [], loading: true, failed: false });

  useEffect(() => {
    let cancelled = false;
    // El contenido anterior se queda (atenuado) mientras llega el nuevo, para
    // que la home no salte de altura con cada cambio del selector.
    setState((prev) => ({ ...prev, loading: true }));
    getDeals(DEALS_LIMIT, membershipsKey ? membershipsKey.split(",") : [], section || undefined)
      .then((data) => {
        if (!cancelled) setState({ deals: data || [], loading: false, failed: false });
      })
      .catch(() => {
        if (!cancelled) setState({ deals: [], loading: false, failed: true });
      });
    return () => {
      cancelled = true;
    };
  }, [membershipsKey, section]);

  // Una oferta de una tienda que no entrega en la dirección del usuario no es
  // una oferta para él: se saca, igual que en la grilla de resultados.
  const visibles = stripUnavailableStores(state.deals, hiddenStores).filter((product) =>
    product.available_at_stores.some((offer) => offer.promo_unit_price != null)
  );

  // Sin filtro, una sección vacía o caída se oculta entera (falla abierto: la
  // home sirve igual sin ofertas). Con filtro NO: si desapareciera al elegir
  // una sección, el selector se iría con ella y el usuario no podría volver.
  if (!section && !state.loading && visibles.length === 0) return null;

  const title = (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <h2 className="flex items-center gap-2 font-display text-xl font-bold text-ink">
        <Tag size={20} className="text-state-promo" aria-hidden="true" />
        Mejores descuentos de hoy
      </h2>
      {/* Las secciones salen de GET /categories, igual que el mega-menú: una
          sección nueva en src/shelves.py aparece acá sola. */}
      <select
        value={section}
        onChange={(event) => setSection(event.target.value)}
        aria-label="Filtrar descuentos por sección"
        className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink"
      >
        <option value="">Todas las secciones</option>
        {sections.map((s) => (
          <option key={s.section} value={s.section}>
            {s.section}
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <section className={`mt-14 transition-opacity ${state.loading ? "opacity-60" : ""}`}>
      {visibles.length > 0 ? (
        // La key por sección remonta el carrusel: al cambiar de sección vuelve
        // al principio en vez de quedar scrolleado a mitad de la lista vieja.
        <ProductCarousel key={section} products={visibles} label="Mejores descuentos de hoy" title={title} />
      ) : (
        <>
          <div className="mb-4">{title}</div>
          <p className="py-8 text-center text-sm text-ink-muted">
            {state.loading
              ? "Buscando descuentos…"
              : state.failed
                ? "No pudimos cargar los descuentos. Probá de nuevo en un momento."
                : `No hay descuentos en ${section} hoy.`}
          </p>
        </>
      )}
    </section>
  );
}
