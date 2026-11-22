import { useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { searchProducts, getProductsByShelf } from "../api/products";
import { useProductFilters } from "../hooks/useProductFilters";
import { useShelves } from "../hooks/useShelves";
import { useProfile } from "../context/ProfileContext";
import { storeLabel } from "../utils/formatters";
import { STORES } from "../utils/constants";
import { FiltersSidebar } from "../components/plp/FiltersSidebar";
import { SortDropdown } from "../components/plp/SortDropdown";
import { ProductGrid } from "../components/plp/ProductGrid";
import { Pagination } from "../components/plp/Pagination";

const NO_DIETARY_FILTERS = { glutenFree: false, vegan: false };

export function SearchResultsPage() {
  const { shelf } = useParams();
  const [searchParams] = useSearchParams();
  const query = searchParams.get("q");
  // "Buscar en todas las góndolas": apaga la detección de góndola de la búsqueda.
  const allShelves = searchParams.get("todas") === "1";
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
      key={`${mode}:${shelf || query}:${allShelves}:${dietary.glutenFree}:${dietary.vegan}`}
      mode={mode}
      shelf={shelf}
      query={query}
      allShelves={allShelves}
      dietary={dietary}
      onToggleDietary={toggleDietary}
    />
  );
}

function ResultsView({ mode, shelf, query, allShelves, dietary, onToggleDietary }) {
  const { labelBySlug, shelves } = useShelves();
  const [results, setResults] = useState(null);
  // Las góndolas donde los filtros dietarios no dicen nada (src/shelves.py). Ahí
  // tampoco se mandan: el estado dietario viene de arriba y sobrevive al cambio
  // de góndola, y un "sin TACC" tildado en Almacén vaciaría Carnes sin verse.
  // Una búsqueda que nombró una de esas góndolas ("asado") cuenta igual.
  const showDietary =
    mode === "shelf"
      ? shelves.find((s) => s.slug === shelf)?.dietary_filters !== false
      : results?.shelf?.dietary_filters !== false;
  const activeDietary = showDietary ? dietary : NO_DIETARY_FILTERS;
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
        ? getProductsByShelf(term, listing, activeDietary, membershipList)
        : searchProducts(term, listing, activeDietary, membershipList, allShelves);
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
  }, [mode, term, allShelves, activeDietary, membershipsKey, listingKey]);

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
  const anyDietaryActive = activeDietary.glutenFree || activeDietary.vegan;
  const emptyMessage = anyDietaryActive
    ? `No encontramos productos en ${title} con los filtros de dieta aplicados.`
    : `No encontramos productos para "${term}" todavía.`;

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6">
      <h1 className="mb-4 font-display text-xl font-bold text-ink">{title}</h1>
      {/* La búsqueda se acotó a la góndola que nombró ("vino tinto" → Vinos):
          si la lectura fue mala, un click la deshace. */}
      {mode === "search" && results?.shelf && (
        <p className="-mt-2 mb-4 text-sm text-ink-muted">
          En {results.shelf.label}.{" "}
          <Link
            to={`/buscar?q=${encodeURIComponent(query)}&todas=1`}
            className="font-semibold text-brand-violet-700 hover:underline"
          >
            Buscar en todas las góndolas
          </Link>
        </p>
      )}

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
          <FiltersSidebar
            filters={filters}
            dietary={dietary}
            onToggleDietary={onToggleDietary}
            showDietary={showDietary}
          />
          <div className="flex-1">
            <div className="mb-4 flex items-center justify-between">
              <p className="text-sm text-ink-muted">
                {loading
                  ? "Buscando productos…"
                  : `${results?.total ?? 0} producto${results?.total === 1 ? "" : "s"}`}
              </p>
              <SortDropdown sortBy={filters.sortBy} onChange={filters.setSortBy} options={filters.SORT_OPTIONS} />
            </div>
            {!loading && (
              <Pagination page={filters.page} totalPages={filters.totalPages} onChange={goToPage} className="mb-4" />
            )}
            {!loading && <ProductGrid products={results?.items || []} emptyMessage={emptyMessage} />}
            {!loading && (
              <Pagination page={filters.page} totalPages={filters.totalPages} onChange={goToPage} className="mt-6" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
