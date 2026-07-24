import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { searchProducts, getProductsByCategory } from "../api/products";
import { useProductFilters } from "../hooks/useProductFilters";
import { FiltersSidebar } from "../components/plp/FiltersSidebar";
import { SortDropdown } from "../components/plp/SortDropdown";
import { ProductGrid } from "../components/plp/ProductGrid";

export function SearchResultsPage() {
  const { bucket } = useParams();
  const [searchParams] = useSearchParams();
  const query = searchParams.get("q");

  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const mode = bucket ? "category" : "search";
  const term = bucket || query;

  useEffect(() => {
    if (!term) {
      setResults([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);

    const request = mode === "category" ? getProductsByCategory(term) : searchProducts(term);
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
  }, [mode, term]);

  const filters = useProductFilters(results);

  const title = mode === "category" ? bucket : `Resultados para "${query}"`;

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6">
      <h1 className="mb-4 font-display text-xl font-bold text-ink">{title}</h1>

      {loading && <p className="text-sm text-ink-muted">Buscando productos…</p>}

      {error && (
        <p className="text-sm text-state-warning">
          No pudimos cargar los resultados. Probá de nuevo en un momento.
        </p>
      )}

      {!loading && !error && (
        <div className="flex flex-col gap-6 lg:flex-row">
          <FiltersSidebar filters={filters} />
          <div className="flex-1">
            <div className="mb-4 flex items-center justify-between">
              <p className="text-sm text-ink-muted">
                {filters.filteredResults.length} producto
                {filters.filteredResults.length === 1 ? "" : "s"}
              </p>
              <SortDropdown sortBy={filters.sortBy} onChange={filters.setSortBy} options={filters.SORT_OPTIONS} />
            </div>
            <ProductGrid
              products={filters.filteredResults}
              emptyMessage={`No encontramos productos para "${term}" todavía.`}
            />
          </div>
        </div>
      )}
    </div>
  );
}
