import { formatPrice, storeLabel } from "../../utils/formatters";

export function BaselineComparison({ result }) {
  const baselines = result.single_store_baselines || {};
  const baselineEntries = Object.entries(baselines);
  if (baselineEntries.length === 0) {
    return (
      <div className="rounded-lg border border-line bg-surface p-4">
        <p className="text-xs text-ink-muted">Gasto total (SmartCart)</p>
        <p className="text-2xl font-bold text-brand-violet-700">{formatPrice(result.total_spent_net)}</p>
      </div>
    );
  }

  const [bestStoreId, bestStoreTotal] = baselineEntries.reduce((best, entry) =>
    entry[1] < best[1] ? entry : best
  );
  const savings = bestStoreTotal - result.total_spent_net;
  // El split multi-tienda no siempre gana: si el carrito es chico, el costo
  // de envío extra de dividirlo puede superar el ahorro en productos. No se
  // fuerza a mostrar "Ahorrás" con un número negativo en ese caso.
  const hasSavings = savings > 0;
  const replacements = (result.baseline_replacements || {})[bestStoreId] || [];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div className="rounded-lg border border-line bg-surface p-4">
        <p className="text-xs text-ink-muted">Gasto total (SmartCart)</p>
        <p className="text-2xl font-bold text-brand-violet-700">{formatPrice(result.total_spent_net)}</p>
      </div>
      <div className="rounded-lg border border-line bg-surface p-4">
        <p className="text-xs text-ink-muted">Comprando todo en {storeLabel(bestStoreId)}</p>
        <p className="text-2xl font-bold text-ink">{formatPrice(bestStoreTotal)}</p>
        {hasSavings ? (
          <p className="text-sm font-semibold text-state-success">Ahorrás {formatPrice(savings)}</p>
        ) : (
          <p className="text-sm font-semibold text-state-warning">
            En este carrito, comprar todo en {storeLabel(bestStoreId)} sale {formatPrice(-savings)} más barato
            (el envío dividido entre tiendas no compensa el ahorro en productos).
          </p>
        )}
        {replacements.length > 0 && (
          <details className="mt-2 text-xs text-ink-muted">
            <summary className="cursor-pointer select-none">Se usaron reemplazos equivalentes</summary>
            <ul className="mt-1 list-inside list-disc">
              {replacements.map((replacement) => (
                <li key={`${replacement.original}-${replacement.replacement}`}>
                  {replacement.original} → {replacement.replacement}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}
