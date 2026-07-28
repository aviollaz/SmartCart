import { useEffect, useRef, useState } from "react";
import { previewPrices } from "../api/prices";

const DEBOUNCE_MS = 300;

/**
 * Precio unitario real de un producto para una cantidad dada, contemplando las
 * promociones que recién se activan a partir de cierta cantidad (2da al 50%,
 * 3x2, "llevando 2 c/u a $X").
 *
 * Deliberadamente no pide nada con quantity <= 1: a una unidad casi ninguna
 * promo de volumen aplica, así que precargar la grilla entera sería una request
 * por producto para reproducir el precio base que la card ya tiene. Se pide solo
 * cuando el usuario sube el stepper, que es cuando el dato cambia algo.
 *
 * Devuelve el mínimo entre tiendas, mismo criterio que resolveDisplayPrice().
 */
export function useFlattenedPrice(unifiedId, quantity) {
  const [state, setState] = useState({ data: null, loading: false });
  const cacheRef = useRef(new Map());

  useEffect(() => {
    if (!unifiedId || quantity <= 1) {
      setState({ data: null, loading: false });
      return;
    }

    const cacheKey = `${unifiedId}:${quantity}`;
    if (cacheRef.current.has(cacheKey)) {
      setState({ data: cacheRef.current.get(cacheKey), loading: false });
      return;
    }

    let cancelled = false;
    setState((prev) => ({ ...prev, loading: true }));

    const timer = setTimeout(() => {
      previewPrices([{ unified_id: unifiedId, quantity }])
        .then((matrix) => {
          const best = pickCheapestStore(matrix?.[unifiedId]);
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
  }, [unifiedId, quantity]);

  return state;
}

function pickCheapestStore(byStore) {
  if (!byStore) return null;

  let best = null;
  for (const [storeId, entry] of Object.entries(byStore)) {
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
