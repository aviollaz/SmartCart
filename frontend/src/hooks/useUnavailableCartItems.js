import { useEffect, useState } from "react";
import { previewPrices } from "../api/prices";
import { useCart } from "../context/CartContext";
import { useProfile } from "../context/ProfileContext";

const EMPTY = [];

/**
 * Los productos del carrito que solo vende una tienda que no entrega en la
 * dirección del usuario.
 *
 * El carrito guarda `{unified_id: {name, quantity}}` y nada más, así que no
 * sabe por sí mismo quién vende cada cosa. El dato sale de POST /price-preview,
 * que devuelve `{unified_id: {store_id: {...}}}`: un producto está afectado si
 * TODAS sus tiendas están en unavailableStores. Se reusa ese endpoint en vez de
 * agregar uno nuevo porque ya devuelve exactamente el mapa producto→tiendas.
 *
 * Es informativo: el carrito no se toca. Cambiar la dirección no puede borrarle
 * al usuario lo que ya eligió — la dirección puede ser un error de tipeo, y el
 * backend igual reporta estos productos como unavailable_products al optimizar.
 *
 * Dos cosas deliberadas:
 * - Sin tiendas excluidas (el caso normal) no se pide nada.
 * - Un unified_id AUSENTE de la respuesta no se marca: /price-preview filtra por
 *   in_stock, así que faltar significa "sin stock en ningún lado", no "no llega".
 *   Marcarlo sería acusar a la dirección de algo que no tiene que ver.
 */
export function useUnavailableCartItems() {
  const { items } = useCart();
  const { unavailableStores } = useProfile();
  const [affected, setAffected] = useState(EMPTY);

  // Claves estables para el efecto: los objetos de items/unavailableStores
  // cambian de identidad en cada render del provider.
  const unifiedIds = Object.keys(items).sort().join(",");
  const excludedKey = unavailableStores.join(",");

  useEffect(() => {
    if (!excludedKey || !unifiedIds) {
      setAffected(EMPTY);
      return;
    }

    const excluded = excludedKey.split(",");
    const ids = unifiedIds.split(",");
    let cancelled = false;

    previewPrices(ids.map((unifiedId) => ({ unified_id: unifiedId, quantity: 1 })))
      .then((matrix) => {
        if (cancelled) return;
        const result = ids.filter((unifiedId) => {
          const stores = Object.keys(matrix?.[unifiedId] || {});
          return stores.length > 0 && stores.every((storeId) => excluded.includes(storeId));
        });
        setAffected(result.length > 0 ? result : EMPTY);
      })
      .catch(() => {
        // Si no se puede confirmar, no se avisa: un falso positivo acá le dice
        // al usuario que un producto no le llega cuando sí le llega.
        if (!cancelled) setAffected(EMPTY);
      });

    return () => {
      cancelled = true;
    };
  }, [unifiedIds, excludedKey]);

  return {
    unavailableStores,
    items: affected.map((unifiedId) => ({ unified_id: unifiedId, name: items[unifiedId]?.name })),
  };
}
