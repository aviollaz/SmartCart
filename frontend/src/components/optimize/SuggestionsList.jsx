import { useState } from "react";
import { Lightbulb } from "lucide-react";
import { formatPrice } from "../../utils/formatters";

function SuggestionRow({ group, onAccept }) {
  const alternatives = group.alternatives || [];
  const [selectedUid, setSelectedUid] = useState(alternatives[0]?.suggested_uid);

  if (alternatives.length === 0) return null;

  const selected = alternatives.find((alt) => alt.suggested_uid === selectedUid) || alternatives[0];

  return (
    <li className="flex flex-col gap-2 border-t border-brand-violet-100 pt-3 first:border-t-0 first:pt-0">
      <p className="text-sm text-ink">
        En lugar de <em>{group.original_product}</em>:
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={selected.suggested_uid}
          onChange={(event) => setSelectedUid(event.target.value)}
          aria-label={`Alternativas para ${group.original_product}`}
          className="min-w-0 flex-1 rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          {alternatives.map((alt) => (
            <option key={alt.suggested_uid} value={alt.suggested_uid}>
              {alt.suggested_product} — ahorrás {formatPrice(alt.savings)}
              {alt.metric_info ? ` (${alt.metric_info})` : ""}
            </option>
          ))}
        </select>

        <button
          type="button"
          onClick={() => onAccept(group.original_uid, selected)}
          className="shrink-0 rounded-md bg-brand-accent px-3 py-1.5 text-sm font-semibold text-white hover:bg-brand-accent-dark"
        >
          Aceptar sugerencia
        </button>
      </div>

      {typeof selected.effective_unit_price === "number" && (
        <p className="text-xs text-ink-muted">
          {formatPrice(selected.effective_unit_price)} por unidad en la tienda más barata.
        </p>
      )}
    </li>
  );
}

export function SuggestionsList({ suggestions, onAccept }) {
  if (!suggestions || suggestions.length === 0) return null;

  return (
    <div className="rounded-lg border border-brand-violet-100 bg-brand-violet-100 p-4">
      <p className="mb-3 flex items-center gap-2 font-display text-sm font-semibold text-brand-violet-700">
        <Lightbulb size={16} />
        Smart Replacements recomendados
      </p>
      <ul className="space-y-3">
        {suggestions.map((group) => (
          <SuggestionRow key={group.original_uid} group={group} onAccept={onAccept} />
        ))}
      </ul>
    </div>
  );
}
