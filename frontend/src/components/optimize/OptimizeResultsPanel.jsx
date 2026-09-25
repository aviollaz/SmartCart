import { ChevronDown, Lightbulb } from "lucide-react";
import { useCart } from "../../context/CartContext";
import { formatPrice } from "../../utils/formatters";
import { LogisticsNotice } from "./LogisticsNotice";
import { SavingsPanel } from "./SavingsPanel";
import { SuggestionsList } from "./SuggestionsList";
import { StoreBreakdownCard } from "./StoreBreakdownCard";
import { StrategicSwapCard } from "./StrategicSwapCard";

/**
 * El resultado de /optimize, de lo más importante a lo menos: cuánto se paga y
 * cuánto se ahorra, si conviene sacar un súper, y dónde comprar cada cosa. Los
 * reemplazos más baratos van plegados al final: sirven (aceptar uno vuelve a
 * optimizar), pero abiertos ocupaban media pantalla antes del botón de compra.
 */
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
      <SavingsPanel result={result} cartItems={items} />
      <StrategicSwapCard suggestion={bestStrategicSwap} onApply={onApplyStrategicSwap} />
      <LogisticsNotice result={result} />

      <div>
        <h3 className="mb-2 font-display text-lg font-bold text-ink">Dónde comprar</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {splitEntries.map(([storeId, checkout]) => (
            <StoreBreakdownCard key={storeId} storeId={storeId} checkout={checkout} cartItems={items} />
          ))}
        </div>
      </div>

      <CollapsedSuggestions suggestions={result.suggestions} onAccept={onAcceptSuggestion} />
    </div>
  );
}

function CollapsedSuggestions({ suggestions, onAccept }) {
  const groups = (suggestions || []).filter((group) => group.alternatives?.length);
  if (groups.length === 0) return null;

  // "Hasta": la mejor alternativa de cada producto, sumadas. No se acepta todo
  // junto, así que es un techo y la frase lo dice.
  const upTo = groups.reduce(
    (sum, group) => sum + Math.max(...group.alternatives.map((alt) => alt.savings || 0)),
    0
  );

  return (
    <details className="group rounded-lg border border-line bg-surface">
      <summary className="flex cursor-pointer select-none items-center justify-between gap-3 px-4 py-3 text-sm text-ink">
        <span className="flex items-center gap-2">
          <Lightbulb size={16} className="shrink-0 text-brand-violet-700" />
          <span>
            Podés ahorrar hasta <strong className="text-state-success">{formatPrice(upTo)}</strong> más
            con {groups.length} reemplazo{groups.length === 1 ? "" : "s"}
          </span>
        </span>
        <ChevronDown size={16} className="shrink-0 transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t border-line p-4">
        <SuggestionsList suggestions={groups} onAccept={onAccept} />
      </div>
    </details>
  );
}
