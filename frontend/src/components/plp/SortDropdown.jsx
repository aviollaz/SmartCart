export function SortDropdown({ sortBy, onChange, options }) {
  return (
    <label className="flex items-center gap-2 text-sm text-ink">
      Ordenar por
      <select
        value={sortBy}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink"
      >
        <option value={options.RELEVANCE}>Relevancia</option>
        <option value={options.PRICE_ASC}>Precio ascendente</option>
        <option value={options.PRICE_DESC}>Precio descendente</option>
      </select>
    </label>
  );
}
