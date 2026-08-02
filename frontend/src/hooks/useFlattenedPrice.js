import { useEffect, useRef, useState } from "react";
import { previewPrices } from "../api/prices";

const DEBOUNCE_MS = 300;

/**
 * Precio unitario real de un producto para una cantidad dada, contemplando las
 * promociones que recién se activan a partir de cierta cantidad (2da al 50%,
 * 3x2, "llevando 2 c/u a $X").
 *
 * Deliberadamente no pide nada con quantity <= 1: el precio a una unidad ya
 * viene resuelto en la respuesta del catálogo (`promo_unit_price` por oferta,
 * calculado con este mismo evaluador en el backend), así que precargar la
 * grilla sería una request por producto para reproducir un dato que la card ya
 * tiene. Se pide solo cuando el usuario sube el stepper, que es cuando aparecen
 * las promos por volumen y el dato realmente cambia.
 *
 * Devuelve el mínimo entre tiendas, mismo criterio que resolveDisplayPrice().
 *
 * `excludeStores` saca del mínimo a las tiendas que no entregan en la dirección
 * del usuario: la respuesta de previewPrices trae todas, y sin esto la card
 * podría anunciar una promo de una tienda cuyas ofertas ya no se listan.
 */
export function useFlattenedPrice(unifiedId, quantity, excludeStores = []) {
  const [state, setState] = useState({ data: null, loading: false });
  const cacheRef = useRef(new Map());
  // Las tiendas excluidas entran como string para poder usarlas de dependencia
  // del efecto sin depender de la identidad del array.
  const excludeKey = excludeStores.join(",");

  useEffect(() => {
    if (!unifiedId || quantity <= 1) {
      setState({ data: null, loading: false });
      return;
    }

    const excluded = excludeKey ? excludeKey.split(",") : [];
    const cacheKey = `${unifiedId}:${quantity}:${excludeKey}`;
    if (cacheRef.current.has(cacheKey)) {
      setState({ data: cacheRef.current.get(cacheKey), loading: false });
      return;
    }

    let cancelled = false;
    setState((prev) => ({ ...prev, loading: true }));

    const timer = setTimeout(() => {
      previewPrices([{ unified_id: unifiedId, quantity }])
        .then((matrix) => {
          const best = pickCheapestStore(matrix?.[unifiedId], excluded);
          cacheRef.current.set(cacheKey, best);
          if (!cancelled) setState({ data: best, loading: false });
        })
        .catch(() => {
          // Un fallo acá no rompe nada: la card sigue mostrando el precio base.
          if (!cancelled) setState({ data: null, loading: false });
        });
    }, DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [unifiedId, quantity, excludeKey]);

  return state;
}

function pickCheapestStore(byStore, excludeStores = []) {
  if (!byStore) return null;

  let best = null;
  for (const [storeId, entry] of Object.entries(byStore)) {
    if (excludeStores.includes(storeId)) continue;
    if (typeof entry?.effective_unit_price !== "number") continue;
    if (!best || entry.effective_unit_price < best.unitPrice) {
      best = {
        storeId,
        unitPrice: entry.effective_unit_price,
        totalCost: entry.total_cost,
        promoDescription: entry.applied_promo_id ? entry.promo_description : null,
      };
    }
  }
  return best;
}
