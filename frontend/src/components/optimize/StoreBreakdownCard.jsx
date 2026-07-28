import { ExternalLink } from "lucide-react";
import { formatPrice, storeLabel } from "../../utils/formatters";
import { PromoTransparency } from "./PromoTransparency";

function readBankDiscount(bankDiscount) {
  if (!bankDiscount) return null;
  return {
    description: bankDiscount.description || "Descuento bancario aplicado",
    amount: bankDiscount.amount ?? 0,
  };
}

export function StoreBreakdownCard({ storeId, checkout, cartItems }) {
  const bankDiscount = readBankDiscount(checkout.bank_discount);
  const productLinks = checkout.products.filter((item) => item.product_url);

  const openAllProducts = () => {
    for (const item of productLinks) {
      window.open(item.product_url, "_blank", "noopener,noreferrer");
    }
  };

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
        productLinks.length > 0 && (
          <button
            type="button"
            onClick={openAllProducts}
            className="mt-3 flex items-center justify-center gap-2 rounded-md bg-brand-accent px-4 py-2 text-sm font-semibold text-white hover:bg-brand-accent-dark"
          >
            Abrir productos de {storeLabel(storeId)}
            <ExternalLink size={14} />
          </button>
        )
      )}

      <details className="mt-3 text-xs text-ink-muted">
        <summary className="cursor-pointer select-none">Ver lista para esta tienda</summary>
        <ul className="mt-1 list-inside list-disc">
          {checkout.products.map((item) => (
            <li key={item.unified_id}>
              {item.product_url ? (
                <a href={item.product_url} target="_blank" rel="noreferrer" className="underline hover:text-brand-violet-700">
                  {cartItems[item.unified_id]?.name || item.unified_id}
                </a>
              ) : (
                cartItems[item.unified_id]?.name || item.unified_id
              )}{" "}
              (x{item.quantity})
            </li>
          ))}
        </ul>
      </details>

      <PromoTransparency checkout={checkout} cartItems={cartItems} />
    </div>
  );
}
