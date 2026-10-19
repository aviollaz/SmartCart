import { useState } from "react";
import { useProfile } from "../context/ProfileContext";
import { STORES } from "../utils/constants";

const SORT_OPTIONS = {
  RELEVANCE: "relevance",
  PRICE_ASC: "price_asc",
  PRICE_DESC: "price_desc",
};

// Estado neutro del filtro de disponibilidad, derivado de la misma lista que
// dibuja los checkboxes para que sumar una tienda sea un solo lugar.
function emptyStoreFilter() {
  return Object.fromEntries(STORES.map((store) => [store.id, false]));
}

/**
 * Estado de los filtros, el orden y la página de una grilla (búsqueda o
 * categoría). NO filtra ni ordena: eso lo hace el backend (`_paginate_listing`
 * en src/api.py), porque el cliente recibe una sola página y unas facetas
 * calculadas acá no verían el resto — una marca fuera de la página 1 no
 * aparecía en el filtro de marcas.
 *
 * `page` es la respuesta del backend (ProductPage): de ahí salen las opciones
 * de marca y los límites del rango de precio. Cambiar cualquier filtro vuelve a
 * la página 1. Para resetear todo al cambiar de búsqueda, el llamador remonta
 * el componente (prop `key`) en vez de sincronizarlo con un efecto.
 */
export function useProductFilters(page) {
  const { unavailableStores, excludedStores, hiddenStores } = useProfile();
  const [selectedBrands, setSelectedBrands] = useState(() => new Set());
  // null = sin filtro de precio (el usuario no tocó el slider).
  const [priceRange, setPriceRangeState] = useState(null);
  const [storeFilter, setStoreFilter] = useState(emptyStoreFilter);
  const [sortBy, setSortByState] = useState(SORT_OPTIONS.RELEVANCE);
  const [pageNumber, setPageNumber] = useState(1);

  const priceBounds = page?.price_bounds || [0, 0];

  // Clampeado en cada render: los límites cambian con los filtros dietarios o
  // la cobertura, y <Range> tira "RangeError: value is smaller than min" si
  // recibe un value fuera de [min, max] aunque sea por un instante.
  const [boundMin, boundMax] = priceBounds;
  const clamp = (v) => Math.min(Math.max(v, boundMin), boundMax);
  const rangeSource = priceRange || priceBounds;
  const effectivePriceRange = [clamp(rangeSource[0]), clamp(rangeSource[1])];

  function toggleBrand(brand) {
    setSelectedBrands((prev) => {
      const next = new Set(prev);
      if (next.has(brand)) next.delete(brand);
      else next.add(brand);
      return next;
    });
    setPageNumber(1);
  }

  function toggleStore(storeId) {
    setStoreFilter((prev) => ({ ...prev, [storeId]: !prev[storeId] }));
    setPageNumber(1);
  }

  function setPriceRange(range) {
    setPriceRangeState(range);
    setPageNumber(1);
  }

  function setSortBy(value) {
    setSortByState(value);
    setPageNumber(1);
  }

  // Lo que viaja a la API. Las marcas y tiendas van ordenadas para que el
  // mismo filtro dé siempre la misma petición.
  const query = {
    page: pageNumber,
    brands: [...selectedBrands].sort(),
    stores: Object.keys(storeFilter).filter((id) => storeFilter[id]).sort(),
    priceRange,
    sort: sortBy,
    hiddenStores,
  };

  return {
    query,
    page: pageNumber,
    setPage: setPageNumber,
    totalPages: page ? Math.max(1, Math.ceil(page.total / page.page_size)) : 1,
    // Separadas para el aviso de la grilla (la causa cambia el texto) y unidas
    // para el filtro por tienda, que no tiene que ofrecer ninguna de las dos.
    unavailableStores,
    excludedStores,
    hiddenStores,
    brandOptions: page?.brands || [],
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
