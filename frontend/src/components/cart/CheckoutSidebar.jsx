import { ChevronDown, CreditCard, Store } from "lucide-react";
import { useProfile } from "../../context/ProfileContext";
import { CARD_OPTIONS, MEMBERSHIP_OPTIONS } from "../../utils/paymentOptions";
import { STORES } from "../../utils/constants";
import { AddressField } from "../profile/AddressField";
import { MultiSelectField } from "../profile/MultiSelectField";
import { OptimizeButton } from "../optimize/OptimizeButton";
import { EstimatedSubtotal } from "./EstimatedSubtotal";

function paymentSummary(cards, memberships) {
  const parts = [];
  if (cards.length) parts.push(`${cards.length} tarjeta${cards.length === 1 ? "" : "s"}`);
  if (memberships.length) parts.push(`${memberships.length} membresía${memberships.length === 1 ? "" : "s"}`);
  return parts.length ? parts.join(" · ") : "Ninguno elegido";
}

function storesSummary(excludedStores, maxStores) {
  const enabled = STORES.filter((store) => !excludedStores.includes(store.id));
  const names = enabled.length === STORES.length ? "Todos" : enabled.map((store) => store.name).join(" y ");
  return maxStores == null ? names : `${names} · máximo ${maxStores}`;
}

/**
 * Qué supermercados puede usar el optimizador. Existe sobre todo por Coto: no
 * permite armar el carrito desde otro sitio (hay que agregar producto por
 * producto), y hay quien prefiere pagar un poco más con tal de no hacerlo.
 *
 * La última tienda marcada queda deshabilitada: sin ninguna no hay nada que
 * optimizar, y el backend lo rechaza igual (422).
 */
function StoresField() {
  const { excludedStores, setExcludedStores, maxStores, setMaxStores } = useProfile();
  const enabledCount = STORES.length - excludedStores.length;

  const toggle = (storeId) => {
    setExcludedStores(
      excludedStores.includes(storeId)
        ? excludedStores.filter((id) => id !== storeId)
        : [...excludedStores, storeId]
    );
  };

  return (
    <details className="group rounded-md border border-line">
      <summary className="flex cursor-pointer select-none items-center justify-between gap-2 px-3 py-2 text-sm">
        <span className="flex items-center gap-2">
          <Store size={16} className="shrink-0 text-brand-accent" />
          <span>
            <span className="block font-semibold text-ink">Supermercados</span>
            <span className="block text-xs text-ink-muted">{storesSummary(excludedStores, maxStores)}</span>
          </span>
        </span>
        <ChevronDown size={16} className="shrink-0 text-ink-muted transition-transform group-open:rotate-180" />
      </summary>
      <fieldset className="flex flex-col gap-2 border-t border-line p-3">
        <legend className="sr-only">Supermercados habilitados</legend>
        {STORES.map((store) => {
          const checked = !excludedStores.includes(store.id);
          const locked = checked && enabledCount === 1;
          return (
            <label key={store.id} className={`flex items-center gap-2 text-sm ${locked ? "text-ink-muted" : "text-ink"}`}>
              <input
                type="checkbox"
                checked={checked}
                disabled={locked}
                onChange={() => toggle(store.id)}
                className="accent-brand-accent"
              />
              {store.name}
            </label>
          );
        })}
        <p className="text-xs text-ink-muted">Los que desmarques no se usan al optimizar ni aparecen en los precios.</p>
        {/* Cada súper del reparto es un checkout aparte. Con una sola tienda
            habilitada no hay nada que limitar. */}
        {enabledCount > 1 && (
          <label className="mt-1 flex items-center justify-between gap-2 text-sm text-ink">
            Comprar en como máximo
            <select
              value={maxStores ?? ""}
              onChange={(event) => setMaxStores(event.target.value ? Number(event.target.value) : null)}
              className="rounded border border-line bg-surface px-2 py-1 text-sm"
            >
              <option value="">Sin límite</option>
              {Array.from({ length: enabledCount - 1 }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>
                  {n} supermercado{n === 1 ? "" : "s"}
                </option>
              ))}
            </select>
          </label>
        )}
      </fieldset>
    </details>
  );
}

/**
 * La columna derecha del carrito: todo lo que hace falta para optimizar, en el
 * orden en que se usa, y el botón siempre a la vista (en desktop es sticky).
 * Antes estos datos eran una sección aparte debajo de la lista, y con un
 * carrito real había que scrollear para llegar al botón.
 *
 * Tarjetas y membresías van plegadas: son 26 + 5 chips, y abiertos empujaban
 * el botón fuera de la pantalla. Las membresías ya se preguntaron en el
 * onboarding (cambian los precios de la grilla); acá se pueden corregir.
 */
export function CheckoutSidebar({ onOpenLocation, subtotalEstimado, onOptimize, disabled, loading }) {
  const { cards, memberships, setCards, setMemberships } = useProfile();

  return (
    <aside className="flex flex-col gap-4 rounded-lg border border-line bg-surface p-5 lg:sticky lg:top-28">
      <AddressField onOpenLocation={onOpenLocation} />

      <details className="group rounded-md border border-line">
        <summary className="flex cursor-pointer select-none items-center justify-between gap-2 px-3 py-2 text-sm">
          <span className="flex items-center gap-2">
            <CreditCard size={16} className="shrink-0 text-brand-accent" />
            <span>
              <span className="block font-semibold text-ink">Medios de pago</span>
              <span className="block text-xs text-ink-muted">{paymentSummary(cards, memberships)}</span>
            </span>
          </span>
          <ChevronDown size={16} className="shrink-0 text-ink-muted transition-transform group-open:rotate-180" />
        </summary>
        <div className="flex flex-col gap-4 border-t border-line p-3">
          <MultiSelectField label="Tarjetas y billeteras" options={CARD_OPTIONS} selected={cards} onChange={setCards} />
          <MultiSelectField
            label="Membresías de supermercados"
            options={MEMBERSHIP_OPTIONS}
            selected={memberships}
            onChange={setMemberships}
          />
        </div>
      </details>

      <StoresField />

      <EstimatedSubtotal subtotalEstimado={subtotalEstimado} />
      <OptimizeButton onClick={onOptimize} disabled={disabled} loading={loading} />
    </aside>
  );
}
