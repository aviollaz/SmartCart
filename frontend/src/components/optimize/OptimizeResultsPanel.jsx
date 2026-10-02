import { useState } from "react";
import { ChevronDown, Lightbulb } from "lucide-react";
import { useCart } from "../../context/CartContext";
import { formatPrice } from "../../utils/formatters";
import { FewerStoresCard } from "./FewerStoresCard";
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
export function OptimizeResultsPanel({ result, maxStores, onAcceptSuggestion, onApplyStrategicSwap, onChooseMaxStores }) {
  const { items } = useCart();
  // Primero las tiendas con carrito por URL (un click y queda armado), al
  // final las que hay que llenar producto por producto (Coto): así el usuario
  // termina lo rápido primero, y la franja que elija en la primera le sirve de
  // referencia para el resto.
  const splitEntries = Object.entries(result.split || {}).sort(
    ([, a], [, b]) => Number(Boolean(b.checkout_url)) - Number(Boolean(a.checkout_url))
  );

  // Qué tiendas ya compró. Estado local, como el checklist de Coto: al
  // re-optimizar el panel se monta de nuevo con otro reparto, y arrastrar las
  // marcas a un reparto distinto sería mentir.
  const [done, setDone] = useState(() => new Set());
  const toggleDone = (storeId) =>
    setDone((prev) => {
      const next = new Set(prev);
      if (next.has(storeId)) next.delete(storeId);
      else next.add(storeId);
      return next;
    });
  const steps = splitEntries.length;

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
      <FewerStoresCard options={result.fewer_stores_options} maxStores={maxStores} onChoose={onChooseMaxStores} />
      <LogisticsNotice result={result} />

      <div>
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="font-display text-lg font-bold text-ink">
            {steps === 1 ? "Dónde comprar" : `Comprá en ${steps} pasos`}
          </h3>
          {steps > 1 && (
            <p className="text-sm text-ink-muted">
              {done.size === steps ? "¡Listo! Completaste todas las compras" : `${done.size} de ${steps} listos`}
            </p>
          )}
        </div>
        {/* Lo que SmartCart no puede hacer por el usuario (pagar, elegir franja)
            sí lo puede abaratar: si ya tiene sesión en la cadena, sus tarjetas
            guardadas aparecen solas. Se dice acá porque es la única pista que
            le ahorra tiempo en cada uno de los checkouts. */}
        <p className="mb-3 text-xs text-ink-muted">
          Cada compra se paga en el sitio del súper. Si ya iniciaste sesión ahí en este navegador, vas a ver tus
          tarjetas guardadas{steps > 1 ? "; tratá de elegir la misma franja de entrega en todos" : ""}.
        </p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {splitEntries.map(([storeId, checkout], index) => (
            <StoreBreakdownCard
              key={storeId}
              storeId={storeId}
              checkout={checkout}
              cartItems={items}
              step={steps > 1 ? index + 1 : null}
              done={done.has(storeId)}
              onToggleDone={() => toggleDone(storeId)}
            />
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
