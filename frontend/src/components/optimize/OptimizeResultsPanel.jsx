import { useCart } from "../../context/CartContext";
import { LogisticsNotice } from "./LogisticsNotice";
import { SavingsPanel } from "./SavingsPanel";
import { SuggestionsList } from "./SuggestionsList";
import { StoreBreakdownCard } from "./StoreBreakdownCard";
import { StrategicSwapCard } from "./StrategicSwapCard";

export function OptimizeResultsPanel({ result, onAcceptSuggestion, onApplyStrategicSwap }) {
  const { items } = useCart();
  const splitEntries = Object.entries(result.split || {});

  // Sólo la de mayor ahorro (el backend las ordena descendente). Todas se
  // calcularon contra el mismo carrito original y son mutuamente excluyentes:
  // apenas se aplica una, las demás quedan describiendo un carrito que ya no
  // existe. Como aplicarla vuelve a optimizar, si todavía queda otra oportunidad
  // el backend la emite sola en la corrida siguiente.
  const [bestStrategicSwap] = result.strategic_swaps || [];

  return (
    <div className="flex flex-col gap-4">
      <StrategicSwapCard suggestion={bestStrategicSwap} onApply={onApplyStrategicSwap} />
      <SavingsPanel result={result} cartItems={items} />
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
