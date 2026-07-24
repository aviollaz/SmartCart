import { BrandFacet } from "./BrandFacet";
import { PriceRangeSlider } from "./PriceRangeSlider";
import { StoreAvailabilityToggle } from "./StoreAvailabilityToggle";

// Sin botón "Aplicar": a diferencia de Carrefour (donde cada filtro implica
// un round-trip al servidor), acá los facets se calculan sobre un resultado
// ya fetcheado en memoria, así que cada cambio filtra al instante.
export function FiltersSidebar({ filters }) {
  const { brandOptions, selectedBrands, toggleBrand, priceBounds, priceRange, setPriceRange, storeFilter, toggleStore } =
    filters;

  return (
    <aside className="w-full shrink-0 lg:w-64">
      <h2 className="mb-2 font-display text-lg font-bold text-ink">Filtros</h2>
      <BrandFacet brandOptions={brandOptions} selectedBrands={selectedBrands} onToggle={toggleBrand} />
      <PriceRangeSlider bounds={priceBounds} value={priceRange} onChange={setPriceRange} />
      <StoreAvailabilityToggle storeFilter={storeFilter} onToggle={toggleStore} />
    </aside>
  );
}
