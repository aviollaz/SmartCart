import { useState } from "react";
import { ChevronDown, SlidersHorizontal } from "lucide-react";
import { BrandFacet } from "./BrandFacet";
import { DietaryFacet } from "./DietaryFacet";
import { PriceRangeSlider } from "./PriceRangeSlider";
import { StoreAvailabilityToggle } from "./StoreAvailabilityToggle";

// Sin botón "Aplicar": cada cambio pide la página 1 con el filtro nuevo. Todos
// los facets se resuelven en el backend (la grilla es una sola página); el
// dietario llega en props aparte porque vive arriba, en SearchResultsPage, y
// sobrevive al cambio de búsqueda.
export function FiltersSidebar({ filters, dietary, onToggleDietary, showDietary = true }) {
  const {
    brandOptions,
    selectedBrands,
    toggleBrand,
    typeOptions,
    selectedTypes,
    toggleType,
    priceBounds,
    priceRange,
    setPriceRange,
    storeFilter,
    toggleStore,
    hiddenStores,
  } = filters;

  // Por debajo de `lg` la sidebar se apila arriba de la grilla, y desplegada
  // ocupaba toda la primera pantalla del celular con marcas: no se veía un solo
  // producto. Ahí arranca plegada detrás de un botón; en desktop va siempre
  // abierta al costado.
  const [open, setOpen] = useState(false);

  return (
    <aside className="w-full shrink-0 lg:w-64">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        className="flex items-center gap-2 rounded-md border border-line px-3 py-2 text-sm font-medium text-ink lg:hidden"
      >
        <SlidersHorizontal size={16} aria-hidden="true" />
        Filtros
        <ChevronDown size={14} className={open ? "rotate-180" : ""} aria-hidden="true" />
      </button>
      <h2 className="mb-2 hidden font-display text-lg font-bold text-ink lg:block">Filtros</h2>
      <div className={`${open ? "mt-3" : "hidden"} lg:mt-0 lg:block`}>
        {/* En carnes y frutas/verduras "sin TACC" o "vegano" no dicen nada. */}
        {showDietary && <DietaryFacet dietary={dietary} onToggle={onToggleDietary} />}
        <BrandFacet
          legend="Tipo de corte"
          brandOptions={typeOptions.map(({ type, count }) => ({ brand: type, count }))}
          selectedBrands={selectedTypes}
          onToggle={toggleType}
        />
        <BrandFacet brandOptions={brandOptions} selectedBrands={selectedBrands} onToggle={toggleBrand} />
        <PriceRangeSlider bounds={priceBounds} value={priceRange} onChange={setPriceRange} />
        <StoreAvailabilityToggle
          storeFilter={storeFilter}
          onToggle={toggleStore}
          unavailableStores={hiddenStores}
        />
      </div>
    </aside>
  );
}
