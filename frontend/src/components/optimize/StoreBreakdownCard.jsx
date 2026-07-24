import { ExternalLink } from "lucide-react";
import { formatPrice, storeLabel } from "../../utils/formatters";

function readBankDiscount(bankDiscount) {
  if (!bankDiscount) return null;
  const description =
    bankDiscount.promo_description || bankDiscount.description || bankDiscount.name || "Descuento bancario aplicado";
  const amount =
    bankDiscount.discount_amount ?? bankDiscount.amount ?? bankDiscount.discount_total ?? bankDiscount.value ?? 0;
  return { description, amount };
}

export function StoreBreakdownCard({ storeId, checkout, cartItems }) {
  const bankDiscount = readBankDiscount(checkout.bank_discount);

  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className="mb-2 font-display text-sm font-bold text-brand-violet-700">{storeLabel(storeId)}</p>
      <dl className="space-y-1 text-sm text-ink">
        <div className="flex justify-between">
          <dt className="text-ink-muted">Subtotal productos</dt>
          <dd>{formatPrice(checkout.subtotal_products)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-muted">Costo de envío</dt>
          <dd>{formatPrice(checkout.delivery_cost)}</dd>
        </div>
        {bankDiscount && (
          <div className="flex justify-between text-state-success">
            <dt>{bankDiscount.description}</dt>
            <dd>-{formatPrice(bankDiscount.amount)}</dd>
          </div>
        )}
        <div className="flex justify-between border-t border-line pt-1 font-semibold">
          <dt>Total tienda</dt>
          <dd>{formatPrice(checkout.store_total)}</dd>
        </div>
      </dl>

      {checkout.checkout_url ? (
        <a
          href={checkout.checkout_url}
          target="_blank"
          rel="noreferrer"
          className="mt-3 flex items-center justify-center gap-2 rounded-md bg-brand-accent px-4 py-2 text-sm font-semibold text-white hover:bg-brand-accent-dark"
        >
          Comprar carrito en Día
          <ExternalLink size={14} />
        </a>
      ) : (
        storeId === "coto_online" && (
          <p className="mt-3 text-xs text-ink-muted">Para Coto, los productos deben agregarse manualmente.</p>
        )
      )}

      <details className="mt-3 text-xs text-ink-muted">
        <summary className="cursor-pointer select-none">Ver lista para esta tienda</summary>
        <ul className="mt-1 list-inside list-disc">
          {checkout.products.map((item) => (
            <li key={item.unified_id}>
              {cartItems[item.unified_id]?.name || item.unified_id} (x{item.quantity})
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
