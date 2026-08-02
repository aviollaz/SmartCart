/**
 * Saca del catálogo las ofertas de tiendas que no entregan en la dirección del
 * usuario (ver `unavailableStores` en ProfileContext).
 *
 * No alcanza con esconder las cards: un producto que venden las dos tiendas
 * sigue siendo comprable, así que se le quita solo la oferta muerta y se
 * descarta el producto entero únicamente si era exclusivo de esa tienda.
 *
 * `min_price` se anula a propósito. GET /category lo calcula en el backend
 * incluyendo a todas las tiendas, así que describe una oferta que ya no está
 * listada. Hoy resolveDisplayPrice() solo lo usa de fallback (cuando no queda
 * ninguna oferta con precio), pero anularlo sigue siendo lo correcto: es un
 * dato falso para el producto recortado.
 */
export function stripUnavailableStores(products, unavailableStores) {
  // Se devuelve el mismo array (misma referencia) cuando no hay nada que sacar:
  // useProductFilters resetea sus facets con un useEffect sobre [results], y un
  // array nuevo en cada render los estaría reseteando para siempre.
  if (!unavailableStores || unavailableStores.length === 0) return products;

  const result = [];
  for (const product of products) {
    const offers = product.available_at_stores || [];
    const kept = offers.filter((offer) => !unavailableStores.includes(offer.store_id));
    if (kept.length === offers.length) {
      result.push(product);
    } else if (kept.length > 0) {
      result.push({ ...product, available_at_stores: kept, min_price: null });
    }
    // kept.length === 0 → producto exclusivo de una tienda que no entrega: se omite.
  }
  return result;
}
