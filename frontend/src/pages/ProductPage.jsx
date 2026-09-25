import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ChevronDown, ExternalLink, ShoppingCart } from "lucide-react";
import { getProductsByIds } from "../api/products";
import { useCart } from "../context/CartContext";
import { useProfile } from "../context/ProfileContext";
import { useProductPricing } from "../hooks/useProductPricing";
import { formatPrice, resolveDisplayImage, storeName } from "../utils/formatters";
import { stripUnavailableStores } from "../utils/storeAvailability";
import { DietaryBadges } from "../components/plp/DietaryBadges";
import { PriceBlock } from "../components/plp/PriceBlock";
import { QuantityStepper } from "../components/plp/QuantityStepper";

/**
 * Ficha de un producto, con el layout de la de Carrefour: foto a la izquierda,
 * precio y compra a la derecha, especificaciones debajo.
 *
 * Reusa POST /products/by-ids con un solo id, y hereda su contrato: un id
 * ausente de la respuesta es un producto que el pruning borró, no un error.
 *
 * No hay rating ni descripción, a propósito. Rating: no existe el dato, e
 * inventarlo es lo último que se le muestra a alguien que está evaluando el
 * producto. Descripción: los scrapers la descartan, porque la de VTEX lista
 * productos hermanos en la misma línea (ver los flags dietarios en CLAUDE.md);
 * traerla es un cambio de scraper y de esquema, anotado en docs/TODO.md.
 */
export function ProductPage() {
  const { unifiedId } = useParams();
  const { memberships, unavailableStores } = useProfile();
  const membershipsKey = (memberships || []).join(",");
  const [state, setState] = useState({ status: "loading", product: null });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading", product: null });
    getProductsByIds([unifiedId], membershipsKey ? membershipsKey.split(",") : [])
      .then((data) => {
        if (cancelled) return;
        setState(data.length ? { status: "ok", product: data[0] } : { status: "missing", product: null });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error", product: null });
      });
    return () => {
      cancelled = true;
    };
  }, [unifiedId, membershipsKey]);

  if (state.status === "loading") {
    return <PageShell><p className="text-sm text-ink-muted">Cargando producto…</p></PageShell>;
  }
  if (state.status === "missing") {
    return (
      <PageShell>
        <p className="text-sm text-ink">Este producto ya no está en el catálogo de ningún supermercado.</p>
      </PageShell>
    );
  }
  if (state.status === "error") {
    return (
      <PageShell>
        <p className="text-sm text-state-warning">No pudimos cargar el producto. Probá de nuevo en un momento.</p>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <ProductDetail product={state.product} unavailableStores={unavailableStores} />
    </PageShell>
  );
}

function PageShell({ children }) {
  const navigate = useNavigate();
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="mb-4 flex items-center gap-1 text-sm font-semibold text-brand-violet-700 hover:underline"
      >
        <ArrowLeft size={16} />
        Volver
      </button>
      {children}
    </div>
  );
}

function ProductDetail({ product: rawProduct, unavailableStores }) {
  // El precio se resuelve sobre las tiendas que entregan; la lista de tiendas
  // de abajo sí las muestra todas, marcando las que no llegan, porque "está en
  // Coto pero Coto no te entrega" es información y no ruido.
  const [visible] = stripUnavailableStores([rawProduct], unavailableStores);
  const product = visible || { ...rawProduct, available_at_stores: [], min_price: null, unit_price: null };

  const { addItem, incrementItem, decrementItem } = useCart();
  const pricing = useProductPricing(product);
  const image = resolveDisplayImage(rawProduct);
  const noStoreDelivers = product.available_at_stores.length === 0;

  return (
    <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
      <div className="flex flex-col gap-6">
        <div className="flex aspect-square items-center justify-center rounded-lg border border-line bg-surface p-6">
          {image ? (
            <img src={image} alt={rawProduct.name} className="h-full w-full object-contain" />
          ) : (
            <span className="text-sm text-ink-muted">Sin foto</span>
          )}
        </div>
        <SpecsTable product={rawProduct} className="hidden md:block" />
      </div>

      <div className="flex flex-col gap-4">
        <div>
          {rawProduct.brand && (
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{rawProduct.brand}</p>
          )}
          <h1 className="font-display text-2xl font-bold text-ink">{rawProduct.name}</h1>
          <DietaryBadges product={rawProduct} className="mt-2" />
        </div>

        {noStoreDelivers ? (
          <p className="text-sm text-state-warning">Ningún supermercado que entrega en tu dirección tiene este producto.</p>
        ) : (
          <div className="flex flex-wrap items-end justify-between gap-4 rounded-lg border border-line bg-surface p-4">
            <PriceBlock product={product} pricing={pricing} size="lg" />
            {pricing.cartEntry ? (
              <QuantityStepper
                quantity={pricing.cartEntry.quantity}
                onIncrement={() => incrementItem(product.unified_id)}
                onDecrement={() => decrementItem(product.unified_id)}
              />
            ) : (
              <button
                type="button"
                onClick={() => addItem(product.unified_id, product.name, 1)}
                className="flex items-center gap-2 rounded-md bg-brand-accent px-6 py-2.5 text-sm font-semibold text-white hover:bg-brand-accent-dark"
              >
                <ShoppingCart size={16} />
                Agregar
              </button>
            )}
          </div>
        )}

        <StoreOffers offers={rawProduct.available_at_stores} unavailableStores={unavailableStores} />
        <SpecsTable product={rawProduct} className="md:hidden" />
      </div>
    </div>
  );
}

function StoreOffers({ offers, unavailableStores }) {
  const sorted = [...(offers || [])].sort(
    (a, b) => (a.promo_unit_price ?? a.base_price) - (b.promo_unit_price ?? b.base_price)
  );
  if (sorted.length === 0) return null;

  return (
    <details className="group rounded-lg border border-line bg-surface">
      <summary className="flex cursor-pointer select-none items-center justify-between px-4 py-3 text-sm font-semibold text-ink">
        En qué supermercados está ({sorted.length})
        <ChevronDown size={16} className="transition-transform group-open:rotate-180" />
      </summary>
      <ul className="divide-y divide-line border-t border-line">
        {sorted.map((offer) => {
          const noDelivery = unavailableStores.includes(offer.store_id);
          const unavailable = noDelivery || !offer.in_stock;
          // Acá sí van las promos por cantidad ("2da al 50%", "3x2"): la card
          // las dejó de listar y este es su lugar.
          const promos = (offer.promotions || [])
            .map((p) => p.description)
            .filter((d) => d && d !== offer.promo_description);
          return (
            <li key={offer.store_id} className={`px-4 py-3 ${unavailable ? "opacity-60" : ""}`}>
              <div className="flex items-center justify-between gap-3">
                <span className="font-semibold text-ink">{storeName(offer.store_id)}</span>
                <span className="text-right">
                  <span className="font-bold text-ink">{formatPrice(offer.promo_unit_price ?? offer.base_price)}</span>
                  {offer.promo_unit_price != null && (
                    <span className="ml-2 text-xs text-ink-muted line-through">{formatPrice(offer.base_price)}</span>
                  )}
                </span>
              </div>
              {offer.promo_description && (
                <p className="text-xs font-semibold text-state-promo">{offer.promo_description}</p>
              )}
              {promos.map((description) => (
                <p key={description} className="text-xs text-state-promo">{description}</p>
              ))}
              <div className="mt-1 flex items-center justify-between gap-3 text-xs text-ink-muted">
                <span>
                  {noDelivery ? "No entrega en tu dirección" : offer.in_stock ? "Con stock" : "Sin stock hoy"}
                </span>
                {offer.product_url && (
                  <a
                    href={offer.product_url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-1 hover:text-brand-violet-700 hover:underline"
                  >
                    Ver en {storeName(offer.store_id)}
                    <ExternalLink size={12} />
                  </a>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </details>
  );
}

function SpecsTable({ product, className = "" }) {
  const rows = [
    ["EAN", product.ean],
    ["Marca", product.brand],
    [
      "Categoría",
      product.shelf_label && (
        <Link key="shelf" to={`/categoria/${product.shelf}`} className="text-brand-violet-700 hover:underline">
          {product.shelf_label}
        </Link>
      ),
    ],
    ["Contenido", product.size_label],
    // Sólo en afirmativo, mismo criterio que los badges: un "No" sería
    // afirmar algo que el parser nunca vio.
    ["Sin TACC", product.is_gluten_free && "Sí"],
    ["Vegano", product.is_vegan && "Sí"],
  ].filter(([, value]) => value);

  return (
    <section className={className}>
      <h2 className="mb-2 font-display text-base font-bold text-ink">Especificaciones</h2>
      <table className="w-full overflow-hidden rounded-lg border border-line bg-surface text-sm">
        <tbody className="divide-y divide-line">
          {rows.map(([label, value]) => (
            <tr key={label}>
              <th scope="row" className="w-1/3 px-4 py-2 text-left font-normal text-ink-muted">{label}</th>
              <td className="px-4 py-2 text-ink">{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
