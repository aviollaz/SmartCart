import { ArrowRight, ChevronDown, ExternalLink } from "lucide-react";
import { useLocalStorage } from "../../hooks/useLocalStorage";
import { formatPrice, formatPriceWhole, storeName } from "../../utils/formatters";
import { COMPARE_SORTS, COMPARE_SORT_LABELS, sortStores } from "../../utils/storeComparisonSort";
import { ProductChecklist } from "./StoreBreakdownCard";

function formatDay(isoDate) {
  // "T00:00" para que la fecha ISO no se lea en UTC y se corra un día.
  return new Date(`${isoDate}T00:00`).toLocaleDateString("es-AR", { weekday: "long", day: "numeric" });
}

/**
 * El resultado de /compare: una fila por súper con el carrito entero (los
 * faltantes ya reemplazados) y debajo el cartel de dividir si el backend lo
 * ofrece.
 *
 * Cerrada, cada fila dice sólo tres cosas: cuánto sale hoy, cuánto otro día
 * (si una promo bancaria lo abarata) y cuántos de los productos elegidos tiene
 * tal cual. Lo demás —qué se cambia y por qué opciones, qué no tiene, el
 * desglose y el botón de compra— va en el desplegable: con seis tarjetas
 * abiertas no se podía comparar nada de un vistazo.
 */
export function StoreComparison({ result, cartItems, onChooseReplacement, onShowSplit, splitLoading, refreshing }) {
  // Preferencia liviana del navegador: si no hay localStorage, arranca en precio hoy.
  const [sortBy, setSortBy] = useLocalStorage("smartcart_compare_sort_v1", COMPARE_SORTS.PRICE_TODAY);
  const stores = sortStores(result.stores, sortBy);

  const names = Object.fromEntries(Object.entries(cartItems).map(([uid, item]) => [uid, item.name]));
  for (const store of result.stores) {
    for (const line of store.lines) {
      for (const option of line.alternatives || []) names[option.unified_id] = option.name;
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-display text-lg font-bold text-ink">Tu carrito en cada supermercado</h3>
        <label className="flex items-center gap-2 text-sm text-ink">
          Ordenar por
          <select
            value={sortBy}
            onChange={(event) => setSortBy(event.target.value)}
            className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          >
            {Object.values(COMPARE_SORTS).map((value) => (
              <option key={value} value={value}>
                {COMPARE_SORT_LABELS[value]}
              </option>
            ))}
          </select>
        </label>
      </div>

      <ul className={`flex flex-col gap-2 transition-opacity ${refreshing ? "pointer-events-none opacity-60" : ""}`}>
        {stores.map((store) => (
          <StoreCompareRow
            key={store.store_id}
            store={store}
            names={names}
            onChooseReplacement={onChooseReplacement}
          />
        ))}
      </ul>
      {sortBy !== COMPARE_SORTS.FIDELITY && stores.some((store) => store.missing > 0) && (
        <p className="text-xs text-ink-muted">
          Los súper a los que les falta algo van al final: su precio no incluye lo que no tienen.
        </p>
      )}

      <SplitOfferBanner offer={result.split_offer} onShow={onShowSplit} loading={splitLoading} />
    </div>
  );
}

/** Una celda del resumen: etiqueta arriba, valor, y una línea chica siempre
 * reservada para que todas las filas midan lo mismo. */
function SummaryCell({ label, value, note, valueClass = "text-ink", noteClass = "text-ink-muted" }) {
  return (
    <div className="min-w-0">
      <p className="truncate text-xs text-ink-muted">{label}</p>
      <p className={`truncate text-base font-bold sm:text-lg ${valueClass}`}>{value}</p>
      <p className={`h-4 truncate text-xs ${noteClass}`} title={note || undefined}>
        {note}
      </p>
    </div>
  );
}

function StoreCompareRow({ store, names, onChooseReplacement }) {
  const name = (uid) => names[uid] || uid;
  const chosen = store.lines.length;
  const toSwap = store.lines.filter((line) => line.status === "reemplazo");
  const noSwap = store.lines.filter((line) => line.status === "falta");
  const productLinks = (store.products || []).filter((item) => item.product_url);

  const availabilityNote = [
    toSwap.length > 0 && `${toSwap.length} a cambiar`,
    noSwap.length > 0 && `${noSwap.length} sin reemplazo`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <li>
      <details className="group rounded-lg border border-line bg-surface">
        <summary className="flex cursor-pointer select-none list-none items-center gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden">
          {/* En el celular el nombre va arriba: con precios de seis cifras, cuatro
              columnas no entran en una fila y los montos se cortaban. */}
          <div className="min-w-0 flex-1 sm:flex sm:items-center sm:gap-3">
          <p className="mb-1 truncate font-display text-base font-bold text-brand-violet-700 sm:mb-0 sm:w-28 sm:shrink-0">
            {storeName(store.store_id)}
          </p>
          <div className="grid min-w-0 grid-cols-3 gap-3 sm:flex-1">
            <SummaryCell label="Hoy" value={store.total != null ? formatPriceWhole(store.total) : "—"} />
            {/* Entre días sólo cambian los descuentos bancarios. */}
            <SummaryCell
              label="Otro día"
              value={store.best_day ? formatPriceWhole(store.best_day.total) : "—"}
              valueClass={store.best_day ? "text-state-success" : "text-ink-muted"}
              note={store.best_day ? `el ${formatDay(store.best_day.date)}` : "sin promo"}
            />
            <SummaryCell
              label="Disponibles"
              value={`${store.exact}/${chosen}`}
              valueClass={store.exact === chosen ? "text-ink" : "text-state-warning"}
              note={availabilityNote}
              noteClass={noSwap.length > 0 ? "text-state-warning" : "text-ink-muted"}
            />
          </div>
          </div>
          <ChevronDown size={18} className="shrink-0 text-ink-muted transition-transform group-open:rotate-180" />
        </summary>

        <div className="flex flex-col gap-4 border-t border-line p-4 text-sm">
          {toSwap.length > 0 && (
            <section>
              <p className="font-semibold text-ink">Productos a cambiar ({toSwap.length})</p>
              <p className="text-xs text-ink-muted">
                {storeName(store.store_id)} no los vende: elegimos el más parecido. Podés cambiarlo.
              </p>
              <ul className="mt-2 space-y-2">
                {toSwap.map((line) => (
                  <SwapLine
                    key={line.unified_id}
                    line={line}
                    name={name}
                    onChoose={(uid) => onChooseReplacement(store.store_id, line.unified_id, uid)}
                  />
                ))}
              </ul>
            </section>
          )}

          {noSwap.length > 0 && (
            <section>
              <p className="font-semibold text-state-warning">Sin reemplazo posible ({noSwap.length})</p>
              <p className="text-xs text-ink-muted">No tiene nada comparable: no están en el precio.</p>
              <ul className="mt-2 space-y-1">
                {noSwap.map((line) => (
                  <li key={line.unified_id} className="truncate text-ink" title={name(line.unified_id)}>
                    {name(line.unified_id)} <span className="text-ink-muted">x{line.quantity}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {toSwap.length === 0 && noSwap.length === 0 && (
            <p className="text-ink">Tiene todos los productos que elegiste.</p>
          )}

          {store.total != null && <PriceBreakdown store={store} />}

          {store.missing_for_min != null && (
            <p className="text-xs text-state-warning">
              Te faltan {formatPrice(store.missing_for_min)} para el mínimo de compra
            </p>
          )}

          {store.checkout_url ? (
            <a
              href={store.checkout_url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center justify-center gap-2 rounded-md bg-brand-accent px-4 py-2 text-sm font-semibold text-white hover:bg-brand-accent-dark"
            >
              Comprar en {storeName(store.store_id)}
              <ExternalLink size={14} />
            </a>
          ) : (
            productLinks.length > 0 && (
              <ProductChecklist storeId={store.store_id} items={productLinks} productName={(item) => name(item.unified_id)} />
            )
          )}

          <p className="text-xs text-ink-muted">El súper confirma el stock final para tu dirección al cerrar la compra.</p>
        </div>
      </details>
    </li>
  );
}

function PriceBreakdown({ store }) {
  return (
    <dl className="space-y-1 rounded-md bg-surface-muted p-3 text-ink">
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
          <dt>
            {store.bank_discount.title || store.bank_discount.description}
            {store.bank_discount.conditions && (
              <span className="block text-xs text-ink-muted">{store.bank_discount.conditions}</span>
            )}
          </dt>
          <dd className="shrink-0">-{formatPrice(store.bank_discount.amount)}</dd>
        </div>
      )}
      <div className="flex justify-between border-t border-line pt-1 font-semibold">
        <dt>Total hoy</dt>
        <dd>{formatPrice(store.total)}</dd>
      </div>
      {store.best_day && (
        <p className="text-xs text-state-success">
          Comprando el {formatDay(store.best_day.date)} con tu tarjeta: {formatPrice(store.best_day.total)}
        </p>
      )}
    </dl>
  );
}

function SwapLine({ line, name, onChoose }) {
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
          <span className="text-xs text-ink-muted"> · única opción</span>
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
