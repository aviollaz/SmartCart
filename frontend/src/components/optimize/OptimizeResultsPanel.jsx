import { useCart } from "../../context/CartContext";
import { BaselineComparison } from "./BaselineComparison";
import { LogisticsNotice } from "./LogisticsNotice";
import { SuggestionsList } from "./SuggestionsList";
import { StoreBreakdownCard } from "./StoreBreakdownCard";

export function OptimizeResultsPanel({ result, onAcceptSuggestion }) {
  const { items } = useCart();
  const splitEntries = Object.entries(result.split || {});

  return (
    <div className="flex flex-col gap-4">
      <BaselineComparison result={result} />
      <LogisticsNotice result={result} />
      <SuggestionsList suggestions={result.suggestions} onAccept={onAcceptSuggestion} />

      <div>
        <h3 className="mb-2 font-display text-lg font-bold text-ink">Desglose por supermercado</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {splitEntries.map(([storeId, checkout]) => (
            <StoreBreakdownCard key={storeId} storeId={storeId} checkout={checkout} cartItems={items} />
          ))}
        </div>
      </div>
    </div>
  );
}
