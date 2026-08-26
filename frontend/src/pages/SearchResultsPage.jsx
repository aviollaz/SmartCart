import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { searchProducts, getProductsByShelf } from "../api/products";
import { useProductFilters } from "../hooks/useProductFilters";
import { useShelves } from "../hooks/useShelves";
import { storeLabel } from "../utils/formatters";
import { FiltersSidebar } from "../components/plp/FiltersSidebar";
import { SortDropdown } from "../components/plp/SortDropdown";
import { ProductGrid } from "../components/plp/ProductGrid";

const NO_DIETARY_FILTERS = { glutenFree: false, vegan: false };

export function SearchResultsPage() {
  const { shelf } = useParams();
  const { labelBySlug } = useShelves();
  const [searchParams] = useSearchParams();
  const query = searchParams.get("q");

  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dietary, setDietary] = useState(NO_DIETARY_FILTERS);

  const mode = shelf ? "shelf" : "search";
  const term = shelf || query;

  const toggleDietary = useCallback((key) => {
    setDietary((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  // Los dietarios están en las deps porque se resuelven en SQL: cambiarlos
  // implica volver a pedir. El flag `cancelled` evita que una respuesta lenta
  // de un toggle anterior pise a la del toggle actual.
  useEffect(() => {
    if (!term) {
      setResults([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);

    const request =
      mode === "shelf"
        ? getProductsByShelf(term, undefined, dietary)
        : searchProducts(term, undefined, dietary);
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
  }, [mode, term, dietary]);

  const filters = useProductFilters(results);

  // El slug de la URL no es presentable ("yerba-mate"): la etiqueta sale de
  // GET /categories, que ya está cacheado por sesión. Mientras carga se muestra
  // el slug, que es feo pero no queda vacío.
  const title = mode === "shelf" ? labelBySlug[shelf] || shelf : `Resultados para "${query}"`;
  // Sin este aviso, la grilla filtrada por cobertura se ve simplemente más
  // chica y parece que faltan productos.
  const excludedLabel = filters.unavailableStores.map(storeLabel).join(" y ");
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

      {error ? (
        <p className="text-sm text-state-warning">
          No pudimos cargar los resultados. Probá de nuevo en un momento.
        </p>
      ) : (
        // La sidebar se mantiene montada durante el loading: si se desmontara,
        // tildar un filtro dietario haría desaparecer el checkbox recién tocado.
        <div className="flex flex-col gap-6 lg:flex-row">
          <FiltersSidebar filters={filters} dietary={dietary} onToggleDietary={toggleDietary} />
          <div className="flex-1">
            <div className="mb-4 flex items-center justify-between">
              <p className="text-sm text-ink-muted">
                {loading
                  ? "Buscando productos…"
                  : `${filters.filteredResults.length} producto${filters.filteredResults.length === 1 ? "" : "s"}`}
              </p>
              <SortDropdown sortBy={filters.sortBy} onChange={filters.setSortBy} options={filters.SORT_OPTIONS} />
            </div>
            {!loading && <ProductGrid products={filters.filteredResults} emptyMessage={emptyMessage} />}
          </div>
        </div>
      )}
    </div>
  );
}
