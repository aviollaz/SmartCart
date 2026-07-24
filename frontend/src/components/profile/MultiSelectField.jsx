export function MultiSelectField({ label, options, selected, onChange }) {
  function toggle(option) {
    if (selected.includes(option)) onChange(selected.filter((item) => item !== option));
    else onChange([...selected, option]);
  }

  return (
    <fieldset>
      <legend className="mb-2 text-sm font-semibold text-ink">{label}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const isSelected = selected.includes(option);
          return (
            <button
              key={option}
              type="button"
              onClick={() => toggle(option)}
              aria-pressed={isSelected}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                isSelected
                  ? "border-brand-violet-700 bg-brand-violet-700 text-white"
                  : "border-line bg-surface text-ink hover:bg-surface-muted"
              }`}
            >
              {option}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
