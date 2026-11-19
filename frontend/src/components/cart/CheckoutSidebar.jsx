import { CalendarDays, ChevronDown, CreditCard, Store } from "lucide-react";
import { useProfile } from "../../context/ProfileContext";
import { CARD_OPTIONS, MEMBERSHIP_OPTIONS } from "../../utils/paymentOptions";
import { AddressField } from "../profile/AddressField";
import { MultiSelectField } from "../profile/MultiSelectField";
import { StoreToggles, storesSummary } from "../profile/StoreToggles";
import { OptimizeButton } from "../optimize/OptimizeButton";
import { EstimatedSubtotal } from "./EstimatedSubtotal";

function paymentSummary(cards, memberships) {
  const parts = [];
  if (cards.length) parts.push(`${cards.length} tarjeta${cards.length === 1 ? "" : "s"}`);
  if (memberships.length) parts.push(`${memberships.length} membresía${memberships.length === 1 ? "" : "s"}`);
  return parts.length ? parts.join(" · ") : "Ninguno elegido";
}

function StoresField() {
  const { excludedStores, maxStores } = useProfile();

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
      <StoreToggles className="border-t border-line p-3" />
    </details>
  );
}

// Más de 7 no aporta: los descuentos bancarios son por día de la semana.
const PURCHASE_DAYS_OPTIONS = [
  { value: 1, label: "Hoy" },
  { value: 2, label: "Hasta mañana" },
  { value: 3, label: "En los próximos 3 días" },
  { value: 7, label: "Esta semana" },
];

/**
 * Hasta cuándo puede esperar el usuario para comprar. Con más de un día, el
 * backend optimiza cada uno con sus descuentos bancarios y elige el más barato.
 */
function PurchaseDaysField({ value, onChange }) {
  return (
    <label className="flex items-center justify-between gap-2 rounded-md border border-line px-3 py-2 text-sm">
      <span className="flex items-center gap-2 font-semibold text-ink">
        <CalendarDays size={16} className="shrink-0 text-brand-accent" />
        Compro
      </span>
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="bg-transparent text-right text-ink"
      >
        {PURCHASE_DAYS_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
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
export function CheckoutSidebar({
  onOpenLocation,
  subtotalEstimado,
  onOptimize,
  purchaseDays,
  onPurchaseDaysChange,
  disabled,
  loading,
}) {
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
      <PurchaseDaysField value={purchaseDays} onChange={onPurchaseDaysChange} />

      <EstimatedSubtotal subtotalEstimado={subtotalEstimado} />
      <OptimizeButton onClick={onOptimize} disabled={disabled} loading={loading} />
    </aside>
  );
}
