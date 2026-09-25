import { ExternalLink } from "lucide-react";
import { formatPrice, storeName } from "../../utils/formatters";
import { PromoTransparency } from "./PromoTransparency";

function readBankDiscount(bankDiscount) {
  if (!bankDiscount) return null;
  return {
    description: bankDiscount.description || "Descuento bancario aplicado",
    amount: bankDiscount.amount ?? 0,
  };
}

/**
 * Una tienda del reparto. A la vista queda lo que hace falta para comprar
 * —cuántos productos, cuánto, y el botón— y el desglose (subtotal, envío,
 * descuento bancario, lista y promos) va plegado en "Ver detalle": lo lee
 * quien desconfía del total, no todo el mundo.
 */
export function StoreBreakdownCard({ storeId, checkout, cartItems }) {
  const bankDiscount = readBankDiscount(checkout.bank_discount);
  const productLinks = checkout.products.filter((item) => item.product_url);
  const units = checkout.products.reduce((sum, item) => sum + (item.quantity || 0), 0);

  const openAllProducts = () => {
    for (const item of productLinks) {
      window.open(item.product_url, "_blank", "noopener,noreferrer");
    }
  };

  return (
    <div className="flex flex-col rounded-lg border border-line bg-surface p-4">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <p className="font-display text-base font-bold text-brand-violet-700">{storeName(storeId)}</p>
          <p className="text-xs text-ink-muted">
            {checkout.products.length} producto{checkout.products.length === 1 ? "" : "s"}
            {units !== checkout.products.length && ` · ${units} unidades`}
          </p>
        </div>
        <p className="text-xl font-bold text-ink">{formatPrice(checkout.store_total)}</p>
      </div>

      {checkout.checkout_url ? (
        <a
          href={checkout.checkout_url}
          target="_blank"
          rel="noreferrer"
          className="mt-3 flex items-center justify-center gap-2 rounded-md bg-brand-accent px-4 py-2 text-sm font-semibold text-white hover:bg-brand-accent-dark"
        >
          Comprar en {storeName(storeId)}
          <ExternalLink size={14} />
        </a>
      ) : (
        productLinks.length > 0 && (
          <button
            type="button"
            onClick={openAllProducts}
            className="mt-3 flex items-center justify-center gap-2 rounded-md bg-brand-accent px-4 py-2 text-sm font-semibold text-white hover:bg-brand-accent-dark"
          >
            Abrir productos en {storeName(storeId)}
            <ExternalLink size={14} />
          </button>
        )
      )}

      <details className="mt-3 text-xs text-ink-muted">
        <summary className="cursor-pointer select-none">Ver detalle</summary>
        <dl className="mt-2 space-y-1 text-sm text-ink">
          <div className="flex justify-between">
            <dt className="text-ink-muted">Productos</dt>
            <dd>{formatPrice(checkout.subtotal_products)}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-ink-muted">Envío</dt>
            <dd>{formatPrice(checkout.delivery_cost)}</dd>
          </div>
          {bankDiscount && (
            <div className="flex justify-between text-state-success">
              <dt>{bankDiscount.description}</dt>
              <dd>-{formatPrice(bankDiscount.amount)}</dd>
            </div>
          )}
        </dl>

        <ul className="mt-2 list-inside list-disc">
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

        <PromoTransparency checkout={checkout} cartItems={cartItems} />

        {/* La disponibilidad que conoce SmartCart es la que la tienda publica en
            su listado, que es por región por defecto y no por dirección: el
            catálogo puede decir que hay stock y el checkout de la cadena
            contestar "no tiene inventario para tu dirección". */}
        <p className="mt-2">El súper confirma el stock final para tu dirección al cerrar la compra.</p>
      </details>
    </div>
  );
}
