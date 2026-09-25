import { useCart } from "../context/CartContext";
import { useProfile } from "../context/ProfileContext";
import { resolveBestOffer, resolveDisplayPrice } from "../utils/formatters";
import { useFlattenedPrice } from "./useFlattenedPrice";

/**
 * Qué precio anunciar para un producto, y con qué tachado y qué leyenda.
 *
 * Lo comparten la card de la grilla y la página de producto: las dos tienen
 * que decir el mismo número para el mismo producto y la misma cantidad, y la
 * regla (catálogo a una unidad, /price-preview cuando el selector sube) es lo
 * bastante sutil como para no querer dos copias.
 *
 * Devuelve:
 * - `price`: el precio unitario a mostrar grande.
 * - `listPrice`: el tachado, o null. Es el de lista DE LA OFERTA que ganó, no
 *   el mínimo entre tiendas: si Día lista más barato que Coto pero el descuento
 *   lo tiene Coto, tachar el de Día pondría el precio de una tienda al lado del
 *   de la otra.
 * - `storeId` / `promoDescription`: la tienda y la promo que explican el
 *   precio, para la leyenda de abajo.
 * - `byQuantity`: true cuando el precio sale de una promo por cantidad ("c/u
 *   llevando 3"), que la leyenda tiene que nombrar.
 * - `quantity`, `cartEntry`, `pricing` (cargando el precio por cantidad).
 */
export function useProductPricing(product) {
  const { items } = useCart();
  const { unavailableStores, memberships } = useProfile();
  const cartEntry = items[product.unified_id];
  const displayPrice = resolveDisplayPrice(product);

  // Promo que ya está aplicada en el precio del catálogo (descuento directo, el
  // único tipo que rige desde la primera unidad). Las condicionales no entran
  // acá: el backend manda promo_unit_price en null a cantidad 1.
  const bestOffer = resolveBestOffer(product);
  const catalogPromo =
    bestOffer && bestOffer.offer.promo_unit_price != null ? bestOffer.offer : null;

  // La cantidad sale del carrito: antes existía un borrador local que dejaba el
  // stepper en 3 o 4 unidades sin que el producto estuviera agregado.
  const quantity = cartEntry ? cartEntry.quantity : 1;

  const { data: flattened, loading: pricing } = useFlattenedPrice(
    product.unified_id,
    quantity,
    unavailableStores,
    memberships || []
  );

  // Solo se pisa el precio si el aplanado es efectivamente más barato; si la
  // promo no aplica a esta cantidad, queda el precio de catálogo.
  const hasBetterPrice =
    flattened && typeof displayPrice === "number" && flattened.unitPrice < displayPrice - 0.01;

  if (hasBetterPrice) {
    return {
      price: flattened.unitPrice,
      listPrice: displayPrice,
      storeId: flattened.storeId,
      promoDescription: flattened.promoDescription,
      byQuantity: true,
      quantity,
      cartEntry,
      pricing,
    };
  }

  return {
    price: displayPrice,
    listPrice: catalogPromo ? catalogPromo.base_price : null,
    storeId: catalogPromo ? catalogPromo.store_id : null,
    promoDescription: catalogPromo ? catalogPromo.promo_description : null,
    byQuantity: false,
    quantity,
    cartEntry,
    pricing,
  };
}
