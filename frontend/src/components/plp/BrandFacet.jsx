export function BrandFacet({ brandOptions, selectedBrands, onToggle }) {
  if (brandOptions.length === 0) return null;

  return (
    <fieldset className="border-b border-line py-4">
      <legend className="mb-2 font-display text-sm font-semibold text-ink">Marca</legend>
      <ul className="max-h-56 space-y-1.5 overflow-y-auto">
        {brandOptions.map(({ brand, count }) => (
          <li key={brand}>
            <label className="flex cursor-pointer items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                checked={selectedBrands.has(brand)}
                onChange={() => onToggle(brand)}
                className="h-4 w-4 accent-brand-violet-700"
              />
              <span className="flex-1 truncate">{brand}</span>
              <span className="text-ink-muted">({count})</span>
            </label>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}
