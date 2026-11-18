// Grilla de casillas en dos columnas, como la lista de «Supermercados» del
// mismo panel. Antes eran pills con flex-wrap: el ancho de cada nombre decidía
// cuántas entraban por fila (3 en unas, 4 en otras) y la lista no se podía
// recorrer de un vistazo.
//
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
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
        {options.map((option) => (
          <label key={option.value} className="flex min-w-0 items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              checked={selected.includes(option.value)}
              onChange={() => toggle(option.value)}
              className="shrink-0 accent-brand-accent"
            />
            <span className="truncate" title={option.label}>
              {option.label}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
