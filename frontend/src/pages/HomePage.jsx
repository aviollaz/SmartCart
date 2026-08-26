import { Link } from "react-router-dom";
import { useShelves } from "../hooks/useShelves";
import { PurchaseHistorySection } from "../components/history/PurchaseHistorySection";

export function HomePage() {
  // Los atajos son las góndolas reales del catálogo, las mismas del mega-menú.
  // Antes eran cuatro etiquetas hardcodeadas (`DIRECT_MATCH_SHORTCUTS`) que
  // espejaban a mano una constante del backend, y espejaban mal: incluían
  // "Otros", el bucket de descarte donde caía el 80% del catálogo.
  const { shelves } = useShelves();

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-12">
      <div className="text-center">
        <h1 className="mb-3 font-display text-3xl font-bold text-brand-violet-700 sm:text-4xl">
          Comprá inteligente en Coto, Día y Carrefour
        </h1>
        <p className="mx-auto mb-8 max-w-xl text-ink-muted">
          Buscá productos, armá tu changuito y dejá que SmartCart encuentre la combinación de
          supermercados que menos te cuesta.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-3">
          {shelves.map((shelf) => (
            <Link
              key={shelf.slug}
              to={`/categoria/${shelf.slug}`}
              className="rounded-full border border-brand-violet-700 px-4 py-2 text-sm font-medium text-brand-violet-700 hover:bg-brand-violet-100"
            >
              {shelf.label}
            </Link>
          ))}
        </div>
      </div>

      {/* Sin historial no renderiza nada, así que para un usuario nuevo la home
          queda exactamente como era. */}
      <PurchaseHistorySection className="mt-12 text-left" />
    </div>
  );
}
