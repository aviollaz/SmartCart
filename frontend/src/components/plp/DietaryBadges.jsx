/**
 * Solo se muestran en afirmativo: la ausencia del flag significa que el parser
 * no encontró una declaración explícita, no que el producto tenga gluten.
 */
export function DietaryBadges({ product, className = "" }) {
  const labels = [];
  if (product.is_gluten_free) labels.push("Sin TACC");
  if (product.is_vegan) labels.push("Vegano");
  if (labels.length === 0) return null;

  return (
    <ul className={`flex flex-wrap gap-1 ${className}`}>
      {labels.map((label) => (
        <li
          key={label}
          className="rounded-full border border-line px-2 py-0.5 text-[11px] font-semibold text-ink-muted"
        >
          {label}
        </li>
      ))}
    </ul>
  );
}
