import { BrandFacet } from "./BrandFacet";
import { DietaryFacet } from "./DietaryFacet";
import { PriceRangeSlider } from "./PriceRangeSlider";
import { StoreAvailabilityToggle } from "./StoreAvailabilityToggle";

// Sin botón "Aplicar": a diferencia de Carrefour (donde cada filtro implica
// un round-trip al servidor), acá los facets se calculan sobre un resultado
// ya fetcheado en memoria, así que cada cambio filtra al instante.
//
// La excepción es el facet dietario, que sí va al servidor — por eso llega en
// props aparte de `filters` en vez de salir de useProductFilters: la distinción
// entre "vista sobre lo ya traído" y "cambia qué filas existen" tiene que verse.
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
    unavailableStores,
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
        unavailableStores={unavailableStores}
      />
    </aside>
  );
}
