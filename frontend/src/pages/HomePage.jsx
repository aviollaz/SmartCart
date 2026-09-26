import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Search, ShoppingCart, Sparkles, Tag, Wand2 } from "lucide-react";
import { getDeals, getDemoCart } from "../api/products";
import { useShelves } from "../hooks/useShelves";
import { useCart } from "../context/CartContext";
import { useProfile } from "../context/ProfileContext";
import { STORES } from "../utils/constants";
import { stripUnavailableStores } from "../utils/storeAvailability";
import { ProductCarousel } from "../components/plp/ProductCarousel";
import { PurchaseHistorySection } from "../components/history/PurchaseHistorySection";

// Cuántas ofertas trae la home. Van en un carrusel de una sola fila, así que
// traer más no ocupa más pantalla: sólo alarga lo que se puede recorrer con
// las flechas. El backend topea en DEALS_MAX_LIMIT (src/api.py).
const DEALS_LIMIT = 50;

// El recorrido en tres pasos, con el mínimo de palabras. La home tenía antes un
// párrafo por paso y las 49 góndolas debajo, que ya están en el mega-menú: a
// alguien que abre el link sin que nadie se lo explique, eso no le dice qué
// hace la app. Esto sí, de un vistazo.
const PASOS = [
  { Icon: Search, titulo: "Buscá", texto: "lo que comprás siempre" },
  { Icon: ShoppingCart, titulo: "Armá tu changuito", texto: "con las cantidades reales" },
  { Icon: Sparkles, titulo: "Te decimos dónde", texto: "conviene comprar cada cosa" },
];

// Un color por cadena, sólo para el diagrama del reparto. No son los colores
// de marca oficiales ni pretenden serlo.
const STORE_DOT = {
  coto_online: "bg-red-500",
  dia_online: "bg-rose-600",
  carrefour_online: "bg-blue-600",
};

export function HomePage() {
  const { items, mergeItems } = useCart();
  const navigate = useNavigate();
  const [cargandoDemo, setCargandoDemo] = useState(false);
  const itemCount = Object.keys(items).length;

  // El atajo del arranque en frío. Es `mergeItems` y no `restoreItems` por la
  // misma razón que el "Repetir" del historial: la home puede visitarse con el
  // carrito lleno, y un botón que borra lo que había sería una trampa.
  async function probarCarritoDeEjemplo() {
    setCargandoDemo(true);
    try {
      const demo = await getDemoCart();
      if (!demo?.length) return;
      mergeItems(
        Object.fromEntries(demo.map((item) => [item.unified_id, { name: item.name, quantity: item.quantity }]))
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
    <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:py-12">
      <section className="text-center">
        <h1 className="mb-3 font-display text-3xl font-bold text-brand-violet-700 sm:text-4xl">
          Tu changuito, al menor precio
        </h1>
        <p className="mx-auto mb-8 max-w-xl text-ink-muted">
          Comparamos Coto, Día y Carrefour y repartimos tu compra donde sale más barata.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            onClick={probarCarritoDeEjemplo}
            disabled={cargandoDemo}
            className="flex items-center gap-2 rounded-full bg-brand-accent px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-brand-accent-dark disabled:opacity-60"
          >
            <Wand2 size={18} aria-hidden="true" />
            {cargandoDemo ? "Armando el carrito…" : "Probar con un carrito de ejemplo"}
          </button>
          {itemCount > 0 && (
            <Link
              to="/carrito"
              className="flex items-center gap-2 rounded-full border border-brand-violet-700 px-5 py-3 text-sm font-semibold text-brand-violet-700 hover:bg-brand-violet-100"
            >
              Ir a mi carrito ({itemCount})
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
          )}
        </div>
      </section>

      <HowItWorks />
      <DealsSection />

      {/* Sin historial no renderiza nada, así que para un usuario nuevo esto no
          existe. */}
      <PurchaseHistorySection className="mt-12 text-left" />
    </div>
  );
}

function HowItWorks() {
  return (
    <section aria-label="Cómo funciona" className="mt-12">
      <ol className="flex flex-col items-center gap-3 sm:flex-row sm:items-stretch sm:justify-center">
        {PASOS.map(({ Icon, titulo, texto }, indice) => (
          <li key={titulo} className="flex items-center">
            <div className="flex h-full w-56 flex-col items-center rounded-xl border border-line bg-surface px-4 py-5 text-center">
              <span className="mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-brand-violet-100 text-brand-violet-700">
                <Icon size={26} aria-hidden="true" />
              </span>
              <p className="font-display text-base font-bold text-ink">
                <span className="text-brand-accent">{indice + 1}.</span> {titulo}
              </p>
              <p className="text-sm text-ink-muted">{texto}</p>
              {indice === PASOS.length - 1 && <SplitDiagram />}
            </div>
            {indice < PASOS.length - 1 && (
              <ArrowRight
                size={24}
                aria-hidden="true"
                className="ml-3 hidden shrink-0 text-brand-violet-500 sm:block"
              />
            )}
          </li>
        ))}
      </ol>
      <p className="mt-4 text-center text-sm">
        <Link to="/ayuda" className="font-semibold text-brand-violet-700 hover:underline">
          ¿Dudas? Mirá las preguntas frecuentes
        </Link>
      </p>
    </section>
  );
}

// El paso 3 dibujado: un carrito que se reparte en las tres cadenas. Es lo
// único de SmartCart que no hace ninguna otra app, así que es lo que tiene
// que verse sin leer.
function SplitDiagram() {
  return (
    <div className="mt-3 flex items-center gap-2" aria-hidden="true">
      <ShoppingCart size={18} className="text-brand-violet-700" />
      <ArrowRight size={14} className="text-ink-muted" />
      <div className="flex flex-col gap-1">
        {STORES.map((store) => (
          <span key={store.id} className="flex items-center gap-1.5 text-xs font-semibold text-ink">
            <span className={`h-2 w-2 rounded-full ${STORE_DOT[store.id] || "bg-ink-muted"}`} />
            {store.name}
          </span>
        ))}
      </div>
    </div>
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
