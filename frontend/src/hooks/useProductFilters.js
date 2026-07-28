import { useEffect, useMemo, useState } from "react";
import { useProfile } from "../context/ProfileContext";
import { resolveDisplayPrice } from "../utils/formatters";
import { stripUnavailableStores } from "../utils/storeAvailability";

const SORT_OPTIONS = {
  RELEVANCE: "relevance",
  PRICE_ASC: "price_asc",
  PRICE_DESC: "price_desc",
};

function computePriceBounds(results) {
  const prices = results.map(resolveDisplayPrice).filter((p) => typeof p === "number" && p > 0);
  if (prices.length === 0) return [0, 0];
  return [Math.min(...prices), Math.max(...prices)];
}

/**
 * Deriva filtros/orden 100% client-side sobre un resultado ya fetcheado
 * (búsqueda o categoría). Todos los facets salen de datos reales presentes en
 * ProductResponse[] — sin fabricar campos que el backend no provee.
 */
export function useProductFilters(results) {
  const { unavailableStores } = useProfile();
  const [selectedBrands, setSelectedBrands] = useState(() => new Set());
  const [priceRange, setPriceRange] = useState(null);
  const [storeFilter, setStoreFilter] = useState({ coto_online: false, dia_online: false });
  const [sortBy, setSortBy] = useState(SORT_OPTIONS.RELEVANCE);

  // El saneo va acá arriba y no dentro del predicado de filteredResults: los
  // límites de precio, los conteos por marca y el contador "N productos" salen
  // todos de esta misma lista, y si siguieran mirando `results` contarían
  // productos que la grilla ya no muestra.
  const usableResults = useMemo(
    () => stripUnavailableStores(results, unavailableStores),
    [results, unavailableStores]
  );

  const priceBounds = useMemo(() => computePriceBounds(usableResults), [usableResults]);

  // Clampeado en cada render (no solo vía el useEffect de abajo): cuando
  // llegan resultados nuevos, priceBounds cambia sincrónicamente en este
  // mismo render pero el useEffect que resincroniza priceRange recién corre
  // después del commit. Sin este clamp, <Range> podía recibir por un
  // instante un value fuera de [min, max] (ej. 0 con min=915) y tirar
  // "RangeError: value is smaller than min".
  const effectivePriceRange = useMemo(() => {
    const [boundMin, boundMax] = priceBounds;
    const source = priceRange || priceBounds;
    const clamp = (v) => Math.min(Math.max(v, boundMin), boundMax);
    return [clamp(source[0]), clamp(source[1])];
  }, [priceRange, priceBounds]);

  // Cada vez que cambia el set de resultados (nueva búsqueda/categoría),
  // los filtros vuelven a su estado neutro y el rango de precio se re-ancla
  // a los límites del nuevo resultado.
  useEffect(() => {
    setSelectedBrands(new Set());
    setStoreFilter({ coto_online: false, dia_online: false });
    setPriceRange(priceBounds);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [usableResults]);

  const brandOptions = useMemo(() => {
    const counts = new Map();
    for (const product of usableResults) {
      const brand = product.brand || "Sin marca";
      counts.set(brand, (counts.get(brand) || 0) + 1);
    }
    return Array.from(counts.entries())
      .map(([brand, count]) => ({ brand, count }))
      .sort((a, b) => b.count - a.count);
  }, [usableResults]);

  function toggleBrand(brand) {
    setSelectedBrands((prev) => {
      const next = new Set(prev);
      if (next.has(brand)) next.delete(brand);
      else next.add(brand);
      return next;
    });
  }

  function toggleStore(storeId) {
    setStoreFilter((prev) => ({ ...prev, [storeId]: !prev[storeId] }));
  }

  const filteredResults = useMemo(() => {
    const [rangeMin, rangeMax] = effectivePriceRange;
    const anyStoreFilterActive = storeFilter.coto_online || storeFilter.dia_online;

    let filtered = usableResults.filter((product) => {
      const brand = product.brand || "Sin marca";
      if (selectedBrands.size > 0 && !selectedBrands.has(brand)) return false;

      const displayPrice = resolveDisplayPrice(product);
      if (typeof displayPrice === "number" && displayPrice > 0) {
        if (displayPrice < rangeMin || displayPrice > rangeMax) return false;
      }

      if (anyStoreFilterActive) {
        const offers = product.available_at_stores || [];
        const matchesStore = offers.some(
          (offer) => storeFilter[offer.store_id] && offer.in_stock
        );
        if (!matchesStore) return false;
      }

      return true;
    });

    if (sortBy === SORT_OPTIONS.PRICE_ASC) {
      filtered = [...filtered].sort((a, b) => (resolveDisplayPrice(a) || 0) - (resolveDisplayPrice(b) || 0));
    } else if (sortBy === SORT_OPTIONS.PRICE_DESC) {
      filtered = [...filtered].sort((a, b) => (resolveDisplayPrice(b) || 0) - (resolveDisplayPrice(a) || 0));
    }
    // SORT_OPTIONS.RELEVANCE: se preserva el orden devuelto por la API (distance asc.)

    return filtered;
  }, [usableResults, selectedBrands, effectivePriceRange, storeFilter, sortBy]);

  return {
    filteredResults,
    unavailableStores,
    brandOptions,
    selectedBrands,
    toggleBrand,
    priceBounds,
    priceRange: effectivePriceRange,
    setPriceRange,
    storeFilter,
    toggleStore,
    sortBy,
    setSortBy,
    SORT_OPTIONS,
  };
}
