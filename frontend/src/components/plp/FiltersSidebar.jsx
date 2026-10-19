import { BrandFacet } from "./BrandFacet";
import { DietaryFacet } from "./DietaryFacet";
import { PriceRangeSlider } from "./PriceRangeSlider";
import { StoreAvailabilityToggle } from "./StoreAvailabilityToggle";

// Sin botón "Aplicar": cada cambio pide la página 1 con el filtro nuevo. Todos
// los facets se resuelven en el backend (la grilla es una sola página); el
// dietario llega en props aparte porque vive arriba, en SearchResultsPage, y
// sobrevive al cambio de búsqueda.
export function FiltersSidebar({ filters, dietary, onToggleDietary }) {
  const {
    brandOptions,
    selectedBrands,
    toggleBrand,
    priceBounds,
    priceRange,
    setPriceRange,
    storeFilter,
    toggleStore,
    hiddenStores,
  } = filters;

  return (
    <aside className="w-full shrink-0 lg:w-64">
      <h2 className="mb-2 font-display text-lg font-bold text-ink">Filtros</h2>
      <DietaryFacet dietary={dietary} onToggle={onToggleDietary} />
      <BrandFacet brandOptions={brandOptions} selectedBrands={selectedBrands} onToggle={toggleBrand} />
      <PriceRangeSlider bounds={priceBounds} value={priceRange} onChange={setPriceRange} />
      <StoreAvailabilityToggle
        storeFilter={storeFilter}
        onToggle={toggleStore}
        unavailableStores={hiddenStores}
      />
    </aside>
  );
}
