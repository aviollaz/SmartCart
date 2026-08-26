/**
 * Saca del catálogo las ofertas de tiendas que no entregan en la dirección del
 * usuario (ver `unavailableStores` en ProfileContext).
 *
 * No alcanza con esconder las cards: un producto que venden las dos tiendas
 * sigue siendo comprable, así que se le quita solo la oferta muerta y se
 * descarta el producto entero únicamente si era exclusivo de esa tienda.
 *
 * `min_price` y `unit_price` se anulan a propósito: los dos los calcula el
 * backend sobre TODAS las ofertas, así que describen una que ya no está listada.
 * El backend no puede evitarlo —no conoce la cobertura, que vive en
 * ProfileContext— y el error va en la dirección peligrosa: anunciar un precio
 * por kilo de una tienda que no entrega es prometer algo que no se puede
 * comprar. Sin ellos la card cae a las ofertas que quedaron (resolveDisplayPrice)
 * y el precio por unidad simplemente no se muestra.
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
      result.push({ ...product, available_at_stores: kept, min_price: null, unit_price: null });
    }
    // kept.length === 0 → producto exclusivo de una tienda que no entrega: se omite.
  }
  return result;
}
