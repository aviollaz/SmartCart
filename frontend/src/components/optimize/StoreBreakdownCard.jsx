import { useState } from "react";
import { Check, ExternalLink } from "lucide-react";
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
  const productName = (item) => cartItems[item.unified_id]?.name || item.unified_id;

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
          <ProductChecklist storeId={storeId} items={productLinks} productName={productName} />
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

        {/* Sin magic link, la lista con links ya está a la vista arriba
            (ProductChecklist): repetirla acá sería la misma lista dos veces. */}
        {checkout.checkout_url && (
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
        )}

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

/**
 * Los productos de una tienda sin carrito por URL (hoy, Coto), uno por fila.
 *
 * Reemplaza a un botón "Abrir productos" que hacía un `window.open` por
 * producto en el mismo click: el navegador sólo le concede una ventana nueva a
 * cada gesto del usuario, así que desde la segunda las bloqueaba, y la primera
 * vez que alguien lo usaba se encontraba con el aviso de popups bloqueados y
 * una sola pestaña abierta. Acá cada link es su propio click, así que ninguno se
 * bloquea nunca.
 *
 * Por qué no se automatiza: Coto agrega al carrito con un POST a su propia API
 * (`cCarritoActor/addOrRemoveItemToOrderV2`) que depende de las cookies de
 * sesión de coto.com.ar, así que SmartCart no lo puede llamar desde su dominio.
 * Ver el comentario de VTEX_CHECKOUT_DOMAINS en src/api.py.
 *
 * Lo abierto se marca (estado local: al re-optimizar la lista cambia, y
 * arrastrar la marca de un reparto al siguiente sería mentir).
 */
function ProductChecklist({ storeId, items, productName }) {
  const [opened, setOpened] = useState(() => new Set());
  const markOpened = (uid) => setOpened((prev) => new Set(prev).add(uid));

  return (
    <div className="mt-3 rounded-md border border-line p-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-sm font-semibold text-ink">Agregá cada producto en {storeName(storeId)}</p>
        <p className="shrink-0 text-xs text-ink-muted">
          {opened.size} de {items.length}
        </p>
      </div>
      <p className="mt-0.5 text-xs text-ink-muted">
        {storeName(storeId)} no permite armar el carrito desde otro sitio: cada link abre el producto en una pestaña nueva.
      </p>
      <ul className="mt-2 space-y-1">
        {items.map((item) => {
          const done = opened.has(item.unified_id);
          return (
            <li key={item.unified_id}>
              <a
                href={item.product_url}
                target="_blank"
                rel="noreferrer"
                onClick={() => markOpened(item.unified_id)}
                className={`flex items-center gap-2 rounded px-1 py-1 text-sm hover:bg-surface-muted ${
                  done ? "text-ink-muted" : "text-ink"
                }`}
              >
                <span
                  className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                    done ? "border-state-success bg-state-success text-white" : "border-line"
                  }`}
                  aria-hidden="true"
                >
                  {done && <Check size={12} />}
                </span>
                <span className={`flex-1 ${done ? "line-through" : ""}`}>{productName(item)}</span>
                <span className="shrink-0 text-xs text-ink-muted">x{item.quantity}</span>
                <ExternalLink size={12} className="shrink-0 text-ink-muted" />
              </a>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
