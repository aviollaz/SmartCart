import { useEffect, useState } from "react";
import { getProductsByIds } from "../api/products";
import { useProfile } from "../context/ProfileContext";
import { stripUnavailableStores } from "../utils/storeAvailability";

const EMPTY = {};

// Tope de /products/by-ids (MAX_PRODUCTS_BY_IDS en src/api.py). Un carrito con
// más de 100 productos DISTINTOS no existe en la práctica, pero si existiera es
// preferible mostrar el carrito sin precios que partir el pedido en dos y
// dibujar un subtotal a medias, que sería un número mentiroso sin aviso.
const MAX_IDS = 100;

/**
 * Resuelve los productos del carrito contra el catálogo de hoy.
 *
 * Mismo patrón que `useHabitualProducts`, y por el mismo motivo: `CartContext`
 * guarda sólo `{name, quantity}`, así que para mostrar imagen y precio hay que
 * ir a buscarlos. `/products/by-ids` ya devuelve todo lo necesario y ya lo usa
 * el historial — no hace falta endpoint nuevo.
 *
 * Falla abierto: si la request se cae, el carrito se dibuja como antes (nombre
 * y cantidad) en vez de mostrar un error. Los productos son los del carrito, no
 * un resultado de búsqueda: el usuario ya sabe qué eligió, y perder los precios
 * es peor que perder la pantalla sólo si la pantalla también se pierde.
 */
export function useCartProducts(items) {
  const { unavailableStores } = useProfile();
  const [byId, setById] = useState(EMPTY);

  // Se ordena antes de unir: acá el orden NO es información (a diferencia del
  // ranking de habituales), así que reordenar el carrito no tiene por qué
  // disparar un pedido nuevo.
  const idsKey = Object.keys(items).sort().join(",");
  const excludedKey = unavailableStores.join(",");

  useEffect(() => {
    if (!idsKey) {
      setById(EMPTY);
      return;
    }

    const ids = idsKey.split(",");
    if (ids.length > MAX_IDS) {
      setById(EMPTY);
      return;
    }

    const excluded = excludedKey ? excludedKey.split(",") : [];
    let cancelled = false;

    getProductsByIds(ids)
      .then((data) => {
        if (cancelled) return;
        // Se recorta por cobertura igual que la grilla: si la tienda más barata
        // no entrega en esta dirección, su precio no es el precio de nadie.
        const visibles = stripUnavailableStores(data, excluded);
        setById(Object.fromEntries(visibles.map((p) => [p.unified_id, p])));
      })
      .catch(() => {
        if (cancelled) return;
        // Visible para quien desarrolla, invisible para el usuario: un carrito
        // sin precios se ve igual que el de antes de esta feature.
        console.warn("[SmartCart] No se pudieron resolver los precios del carrito.");
        setById(EMPTY);
      });

    return () => {
      cancelled = true;
    };
  }, [idsKey, excludedKey]);

  return byId;
}
