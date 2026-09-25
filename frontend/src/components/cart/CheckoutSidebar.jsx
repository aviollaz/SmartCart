import { ChevronDown, CreditCard } from "lucide-react";
import { useProfile } from "../../context/ProfileContext";
import { CARD_OPTIONS, MEMBERSHIP_OPTIONS } from "../../utils/paymentOptions";
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

      <EstimatedSubtotal subtotalEstimado={subtotalEstimado} />
      <OptimizeButton onClick={onOptimize} disabled={disabled} loading={loading} />
    </aside>
  );
}
