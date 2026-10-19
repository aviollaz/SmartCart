import { ChevronDown, Lightbulb } from "lucide-react";
import { useCart } from "../../context/CartContext";
import { STORES } from "../../utils/constants";
import { formatPrice } from "../../utils/formatters";
import { FewerStoresCard } from "./FewerStoresCard";
import { LogisticsNotice } from "./LogisticsNotice";
import { SavingsPanel } from "./SavingsPanel";
import { SuggestionsList } from "./SuggestionsList";
import { StoreBreakdownCard } from "./StoreBreakdownCard";
import { StrategicSwapCard } from "./StrategicSwapCard";

/**
 * El resultado de /optimize, de lo más importante a lo menos: cuánto se paga y
 * cuánto se ahorra (una tarjeta), las opciones para cambiar el resultado (un
 * desplegable cerrado) y dónde comprar cada cosa. Antes cada opción y cada
 * aviso era su propia tarjeta y el resultado arrancaba con cinco carteles.
 */
export function OptimizeResultsPanel({ result, maxStores, onAcceptSuggestion, onApplyStrategicSwap, onChooseMaxStores }) {
  const { items } = useCart();
  const splitEntries = Object.entries(result.split || {});
  // Envío "(estimado)": la tienda tiene consulta en vivo y esta vez cayó a la
  // tabla por zona.
  const logisticsKey = Object.fromEntries(STORES.map((s) => [s.id, s.key]));

  return (
    <div className="flex flex-col gap-4">
      <SavingsPanel result={result} cartItems={items} maxStores={maxStores} onChooseMaxStores={onChooseMaxStores} />
      <LogisticsNotice result={result} />
      <MoreOptions
        result={result}
        onAcceptSuggestion={onAcceptSuggestion}
        onApplyStrategicSwap={onApplyStrategicSwap}
      />

      <div>
        <h3 className="mb-2 font-display text-lg font-bold text-ink">
          Dónde comprar · {splitEntries.length} supermercado{splitEntries.length === 1 ? "" : "s"}
        </h3>
        <FewerStoresCard options={result.fewer_stores_options} split={result.split} onChoose={onChooseMaxStores} />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {splitEntries.map(([storeId, checkout]) => (
            <StoreBreakdownCard
              key={storeId}
              storeId={storeId}
              checkout={checkout}
              cartItems={items}
              shippingEstimated={result.logistics?.[logisticsKey[storeId]]?.source === "fallback"}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * Todo lo que ahorra más, en un solo desplegable cerrado: sacar una tienda
 * cambiando productos y los reemplazos más baratos por producto. Comprar en
 * menos súper no va acá porque cuesta más: vive bajo "Dónde comprar".
 */
function MoreOptions({ result, onAcceptSuggestion, onApplyStrategicSwap }) {
  // Sólo el cierre de mayor ahorro (el backend las ordena descendente). Todos
  // se calcularon contra el mismo carrito original y son mutuamente
  // excluyentes: apenas se aplica uno, los demás describen un carrito que ya no
  // existe. Como aplicarlo vuelve a optimizar, si queda otra oportunidad el
  // backend la emite sola en la corrida siguiente.
  const [bestStrategicSwap] = (result.strategic_swaps || []).filter((s) => s.swaps?.length);
  const groups = (result.suggestions || []).filter((group) => group.alternatives?.length);
  if (!bestStrategicSwap && groups.length === 0) return null;

  // "Hasta": la mejor alternativa de cada producto, sumadas, o el cierre de
  // tienda si ahorra más. No se aplican todas juntas, así que es un techo y la
  // frase lo dice.
  const suggestionsUpTo = groups.reduce(
    (sum, group) => sum + Math.max(...group.alternatives.map((alt) => alt.savings || 0)),
    0
  );
  const upTo = Math.max(suggestionsUpTo, bestStrategicSwap?.projected_savings || 0);

  return (
    <details className="group rounded-lg border border-line bg-surface">
      <summary className="flex cursor-pointer select-none items-center justify-between gap-3 px-4 py-3 text-sm text-ink">
        <span className="flex items-center gap-2">
          <Lightbulb size={16} className="shrink-0 text-brand-violet-700" />
          <span>
            Podés ahorrar hasta <strong className="text-state-success">{formatPrice(upTo)}</strong> más
          </span>
        </span>
        <ChevronDown size={16} className="shrink-0 transition-transform group-open:rotate-180" />
      </summary>
      <div className="flex flex-col gap-4 border-t border-line p-4">
        <StrategicSwapCard suggestion={bestStrategicSwap} onApply={onApplyStrategicSwap} />
        {groups.length > 0 && (
          <div>
            <p className="mb-2 text-sm font-semibold text-ink">Productos más baratos, misma cantidad</p>
            <SuggestionsList suggestions={groups} onAccept={onAcceptSuggestion} />
          </div>
        )}
      </div>
    </details>
  );
}
