import { ArrowRight, ExternalLink } from "lucide-react";
import { formatPrice, storeName } from "../../utils/formatters";
import { ProductChecklist } from "./StoreBreakdownCard";

function formatDay(isoDate) {
  // "T00:00" para que la fecha ISO no se lea en UTC y se corra un día.
  return new Date(`${isoDate}T00:00`).toLocaleDateString("es-AR", { weekday: "long", day: "numeric" });
}

/**
 * El resultado de /compare: una tarjeta por súper con el carrito entero
 * (los faltantes ya reemplazados), y debajo el cartel de dividir si el backend
 * lo ofrece. Dividir abre la vista del optimizador.
 */
export function StoreComparison({ result, cartItems, onChooseReplacement, onShowSplit, splitLoading }) {
  const names = Object.fromEntries(Object.entries(cartItems).map(([uid, item]) => [uid, item.name]));
  for (const store of result.stores) {
    for (const line of store.lines) {
      for (const option of line.alternatives || []) names[option.unified_id] = option.name;
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <h3 className="font-display text-lg font-bold text-ink">Tu carrito en cada supermercado</h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {result.stores.map((store) => (
          <StoreCompareCard
            key={store.store_id}
            store={store}
            cheapest={store.store_id === result.cheapest}
            names={names}
            onChooseReplacement={onChooseReplacement}
          />
        ))}
      </div>
      <SplitOfferBanner offer={result.split_offer} onShow={onShowSplit} loading={splitLoading} />
    </div>
  );
}

function StoreCompareCard({ store, cheapest, names, onChooseReplacement }) {
  const name = (uid) => names[uid] || uid;
  const total = store.lines.length;
  const counts = [
    `${store.exact}/${total} iguales`,
    store.replaced > 0 && `${store.replaced} reemplazo${store.replaced === 1 ? "" : "s"}`,
    store.missing > 0 && `${store.missing} no ${store.missing === 1 ? "lo" : "los"} tiene`,
  ].filter(Boolean);
  const productLinks = (store.products || []).filter((item) => item.product_url);

  return (
    <div className={`flex flex-col rounded-lg border bg-surface p-4 ${cheapest ? "border-state-success" : "border-line"}`}>
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 font-display text-base font-bold text-brand-violet-700">
            {storeName(store.store_id)}
            {cheapest && (
              <span className="rounded-md bg-state-success px-1.5 py-0.5 text-xs font-semibold text-white">Más barato</span>
            )}
          </p>
          <p className="text-xs text-ink-muted">{counts.join(" · ")}</p>
        </div>
        {store.total != null && <p className="shrink-0 text-xl font-bold text-ink">{formatPrice(store.total)}</p>}
      </div>

      {store.best_day && (
        <p className="mt-1 text-xs text-state-success">
          {/* Entre días sólo cambian los descuentos bancarios. */}
          El {formatDay(store.best_day.date)} con tu tarjeta: {formatPrice(store.best_day.total)}
        </p>
      )}
      {store.missing_for_min != null && (
        <p className="mt-1 text-xs text-state-warning">
          Te faltan {formatPrice(store.missing_for_min)} para el mínimo de compra
        </p>
      )}

      {store.checkout_url ? (
        <a
          href={store.checkout_url}
          target="_blank"
          rel="noreferrer"
          className="mt-3 flex items-center justify-center gap-2 rounded-md bg-brand-accent px-4 py-2 text-sm font-semibold text-white hover:bg-brand-accent-dark"
        >
          Comprar en {storeName(store.store_id)}
          <ExternalLink size={14} />
        </a>
      ) : (
        productLinks.length > 0 && (
          <ProductChecklist storeId={store.store_id} items={productLinks} productName={(item) => name(item.unified_id)} />
        )
      )}

      {store.total != null && (
        <details className="mt-3 text-xs text-ink-muted">
          <summary className="cursor-pointer select-none">Ver detalle</summary>
          <dl className="mt-2 space-y-1 text-sm text-ink">
            <div className="flex justify-between">
              <dt className="text-ink-muted">Productos</dt>
              <dd>{formatPrice(store.subtotal_products)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-ink-muted">Envío</dt>
              <dd>{formatPrice(store.delivery_cost)}</dd>
            </div>
            {store.bank_discount && (
              <div className="flex justify-between gap-3 text-state-success">
                <dt>{store.bank_discount.title || store.bank_discount.description}</dt>
                <dd className="shrink-0">-{formatPrice(store.bank_discount.amount)}</dd>
              </div>
            )}
          </dl>
          <ul className="mt-2 space-y-1">
            {store.lines
              .filter((line) => line.status !== "igual")
              .map((line) => (
                <ReplacementLine
                  key={line.unified_id}
                  line={line}
                  name={name}
                  onChoose={(uid) => onChooseReplacement(store.store_id, line.unified_id, uid)}
                />
              ))}
          </ul>
          <p className="mt-2">El súper confirma el stock final para tu dirección al cerrar la compra.</p>
        </details>
      )}
    </div>
  );
}

function ReplacementLine({ line, name, onChoose }) {
  if (line.status === "falta") {
    return (
      <li className="truncate text-state-warning" title={name(line.unified_id)}>
        No tiene {name(line.unified_id)}
      </li>
    );
  }
  return (
    <li>
      <span className="flex items-center gap-1 truncate text-ink-muted" title={name(line.unified_id)}>
        {name(line.unified_id)}
        <ArrowRight size={12} className="shrink-0" />
      </span>
      {line.alternatives.length > 1 ? (
        <select
          value={line.replacement.unified_id}
          onChange={(event) => onChoose(event.target.value)}
          className="mt-0.5 w-full truncate rounded border border-line bg-surface px-2 py-1 text-sm text-ink"
        >
          {line.alternatives.map((option) => (
            <option key={option.unified_id} value={option.unified_id}>
              {option.name} x{option.quantity} · {formatPrice(option.total_cost)}
            </option>
          ))}
        </select>
      ) : (
        <p className="truncate text-sm text-ink" title={line.replacement.name}>
          {line.replacement.name} x{line.replacement.quantity} · {formatPrice(line.replacement.total_cost)}
        </p>
      )}
    </li>
  );
}

function SplitOfferBanner({ offer, onShow, loading }) {
  if (!offer) return null;
  const stores = offer.stores.map(storeName).join(" y ");
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-brand-accent bg-surface p-4 text-sm text-ink">
      <p>
        {offer.saving != null ? (
          <>
            Dividiendo entre {stores} pagás{" "}
            <strong className="text-state-success">{formatPrice(offer.saving)}</strong> menos
          </>
        ) : (
          <>
            Ningún súper tiene todo: dividiendo entre {stores} comprás todo por{" "}
            <strong>{formatPrice(offer.total_spent_net)}</strong>
          </>
        )}
      </p>
      <button
        type="button"
        onClick={onShow}
        disabled={loading}
        className="shrink-0 rounded-md border border-brand-accent px-4 py-1.5 text-sm font-semibold text-brand-accent hover:bg-brand-accent hover:text-white disabled:opacity-50"
      >
        Ver cómo dividir
      </button>
    </div>
  );
}
