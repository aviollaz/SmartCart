import { Lightbulb } from "lucide-react";
import { formatPrice } from "../../utils/formatters";

export function SuggestionsList({ suggestions }) {
  if (!suggestions || suggestions.length === 0) return null;

  return (
    <div className="rounded-lg border border-brand-violet-100 bg-brand-violet-100 p-4">
      <p className="mb-2 flex items-center gap-2 font-display text-sm font-semibold text-brand-violet-700">
        <Lightbulb size={16} />
        Smart Replacements recomendados
      </p>
      <ul className="space-y-1.5 text-sm text-ink">
        {suggestions.map((suggestion) => (
          <li key={suggestion.suggested_uid}>
            Cambiar <em>{suggestion.original_product}</em> por{" "}
            <strong>{suggestion.suggested_product}</strong> te ahorra{" "}
            <strong>{formatPrice(suggestion.savings)}</strong> extra
            {suggestion.metric_info ? ` (${suggestion.metric_info})` : ""}.
          </li>
        ))}
      </ul>
    </div>
  );
}
