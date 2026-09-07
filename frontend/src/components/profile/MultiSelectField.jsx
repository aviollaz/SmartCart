// `options` son `{value, label}`: el `value` es lo que viaja a /optimize y lo
// que el optimizador compara por igualdad exacta contra los slugs de
// src/promotions/banks.py; el `label` es lo único que se dibuja.
export function MultiSelectField({ label, options, selected, onChange }) {
  function toggle(value) {
    if (selected.includes(value)) onChange(selected.filter((item) => item !== value));
    else onChange([...selected, value]);
  }

  return (
    <fieldset>
      <legend className="mb-2 text-sm font-semibold text-ink">{label}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const isSelected = selected.includes(option.value);
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => toggle(option.value)}
              aria-pressed={isSelected}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                isSelected
                  ? "border-brand-violet-700 bg-brand-violet-700 text-white"
                  : "border-line bg-surface text-ink hover:bg-surface-muted"
              }`}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
