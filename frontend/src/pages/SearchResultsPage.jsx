import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { searchProducts, getProductsByShelf } from "../api/products";
import { useProductFilters } from "../hooks/useProductFilters";
import { useShelves } from "../hooks/useShelves";
import { useProfile } from "../context/ProfileContext";
import { storeLabel } from "../utils/formatters";
import { STORES } from "../utils/constants";
import { FiltersSidebar } from "../components/plp/FiltersSidebar";
import { SortDropdown } from "../components/plp/SortDropdown";
import { ProductGrid } from "../components/plp/ProductGrid";

const NO_DIETARY_FILTERS = { glutenFree: false, vegan: false };

export function SearchResultsPage() {
  const { shelf } = useParams();
  const [searchParams] = useSearchParams();
  const query = searchParams.get("q");
  const [dietary, setDietary] = useState(NO_DIETARY_FILTERS);

  const toggleDietary = useCallback((key) => {
    setDietary((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  // El `key` remonta la vista al cambiar de búsqueda, de góndola o de filtro
  // dietario, y con eso vuelven a cero los filtros, el orden y la página — sin
  // un efecto que los resetee después de que ya salió una petición con los
  // filtros viejos. Los dietarios viven acá arriba porque sobreviven al cambio
  // de búsqueda.
  const mode = shelf ? "shelf" : "search";
  return (
    <ResultsView
      key={`${mode}:${shelf || query}:${dietary.glutenFree}:${dietary.vegan}`}
      mode={mode}
      shelf={shelf}
      query={query}
      dietary={dietary}
      onToggleDietary={toggleDietary}
    />
  );
}

function ResultsView({ mode, shelf, query, dietary, onToggleDietary }) {
  const { labelBySlug } = useShelves();
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { memberships } = useProfile();
  // String y no el array: la identidad del array cambia con cada render del
  // provider y relanzaría la búsqueda sin que nada haya cambiado.
  const membershipsKey = (memberships || []).join(",");

  const term = shelf || query;

  const filters = useProductFilters(results);
  // Misma razón que membershipsKey: el objeto se arma en cada render.
  const listingKey = JSON.stringify(filters.query);

  // Todo lo que cambia qué filas vuelven está en las deps, porque se resuelve en
  // el backend. El flag `cancelled` evita que una respuesta lenta de un cambio
  // anterior pise a la del actual.
  useEffect(() => {
    if (!term) {
      setResults(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);

    const listing = JSON.parse(listingKey);
    const membershipList = membershipsKey.split(",").filter(Boolean);
    const request =
      mode === "shelf"
        ? getProductsByShelf(term, listing, dietary, membershipList)
        : searchProducts(term, listing, dietary, membershipList);
    request
      .then((data) => {
        if (!cancelled) setResults(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [mode, term, dietary, membershipsKey, listingKey]);

  function goToPage(page) {
    filters.setPage(page);
    window.scrollTo({ top: 0 });
  }

  // El slug de la URL no es presentable ("yerba-mate"): la etiqueta sale de
  // GET /categories, que ya está cacheado por sesión. Mientras carga se muestra
  // el slug, que es feo pero no queda vacío.
  const title = mode === "shelf" ? labelBySlug[shelf] || shelf : `Resultados para "${query}"`;
  // Sin este aviso, la grilla filtrada por cobertura se ve simplemente más
  // chica y parece que faltan productos.
  const excludedLabel = filters.unavailableStores.map(storeLabel).join(" y ");
  // Las tiendas con aviso (constants.js) arrancan deshabilitadas sin que el
  // usuario haya hecho nada, así que "lo deshabilitaste" sería falso para ellas.
  const disabledIds = filters.excludedStores.filter((id) => !filters.unavailableStores.includes(id));
  const isWarned = (id) => STORES.some((store) => store.id === id && store.warning);
  const disabledLabel = disabledIds.filter((id) => !isWarned(id)).map(storeLabel).join(" y ");
  const warnedLabel = disabledIds.filter(isWarned).map(storeLabel).join(" y ");
  const anyDietaryActive = dietary.glutenFree || dietary.vegan;
  const emptyMessage = anyDietaryActive
    ? `No encontramos productos en ${title} con los filtros de dieta aplicados.`
    : `No encontramos productos para "${term}" todavía.`;

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6">
      <h1 className="mb-4 font-display text-xl font-bold text-ink">{title}</h1>

      {excludedLabel && (
        <p className="mb-4 rounded-md border border-state-warning/40 bg-state-warning/10 px-3 py-2 text-sm text-ink-muted">
          No mostramos productos de <strong className="text-ink">{excludedLabel}</strong>: no entregan en tu dirección.
        </p>
      )}
      {disabledLabel && (
        <p className="mb-4 rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink-muted">
          No mostramos productos de <strong className="text-ink">{disabledLabel}</strong>: lo deshabilitaste en el carrito.
        </p>
      )}
      {warnedLabel && (
        <p className="mb-4 rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink-muted">
          No mostramos productos de <strong className="text-ink">{warnedLabel}</strong>: viene deshabilitado por
          seguridad. Podés habilitarlo en el carrito, en "Supermercados".
        </p>
      )}

      {error ? (
        <p className="text-sm text-state-warning">
          No pudimos cargar los resultados. Probá de nuevo en un momento.
        </p>
      ) : (
        // La sidebar se mantiene montada durante el loading: si se desmontara,
        // tildar un filtro dietario haría desaparecer el checkbox recién tocado.
        <div className="flex flex-col gap-6 lg:flex-row">
          <FiltersSidebar filters={filters} dietary={dietary} onToggleDietary={onToggleDietary} />
          <div className="flex-1">
            <div className="mb-4 flex items-center justify-between">
              <p className="text-sm text-ink-muted">
                {loading
                  ? "Buscando productos…"
                  : `${results?.total ?? 0} producto${results?.total === 1 ? "" : "s"}`}
              </p>
              <SortDropdown sortBy={filters.sortBy} onChange={filters.setSortBy} options={filters.SORT_OPTIONS} />
            </div>
            {!loading && <ProductGrid products={results?.items || []} emptyMessage={emptyMessage} />}
            {!loading && filters.totalPages > 1 && (
              <nav className="mt-6 flex items-center justify-center gap-4 text-sm text-ink">
                <button
                  type="button"
                  onClick={() => goToPage(filters.page - 1)}
                  disabled={filters.page <= 1}
                  className="rounded-md border border-line px-3 py-1.5 hover:bg-surface-muted disabled:opacity-40"
                >
                  ‹ Anterior
                </button>
                <span className="text-ink-muted">
                  Página {filters.page} de {filters.totalPages}
                </span>
                <button
                  type="button"
                  onClick={() => goToPage(filters.page + 1)}
                  disabled={filters.page >= filters.totalPages}
                  className="rounded-md border border-line px-3 py-1.5 hover:bg-surface-muted disabled:opacity-40"
                >
                  Siguiente ›
                </button>
              </nav>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
