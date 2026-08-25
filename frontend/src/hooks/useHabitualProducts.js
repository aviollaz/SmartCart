import { useEffect, useState } from "react";
import { getProductsByIds } from "../api/products";
import { useProfile } from "../context/ProfileContext";
import { stripUnavailableStores } from "../utils/storeAvailability";

const EMPTY = [];

/**
 * Resuelve el ranking de habituales (unified_ids) contra el catálogo de hoy.
 *
 * Devuelve `{ products, missing, loading }`:
 * - `products`: los que siguen existiendo, ya recortados por cobertura.
 * - `missing`: los que el pruning del scraper borró del catálogo.
 *
 * Falla abierto: si la request se cae, la sección no se renderiza. Es una
 * sección "linda de tener" en la home, y un 500 de la API no puede ponerle un
 * cartel de error a la pantalla de entrada. (El endpoint sí falla ruidoso; el
 * que falla abierto es este consumidor — misma división que coto_logistics.py.)
 */
export function useHabitualProducts(habituales) {
  const { unavailableStores } = useProfile();
  const [state, setState] = useState({ products: EMPTY, missing: EMPTY, loading: false });

  // Clave estable para el efecto. A diferencia de useUnavailableCartItems, acá
  // NO se ordena antes de unir: el orden ES el ranking, así que un reordenamiento
  // es un cambio real y tiene que volver a pedir.
  const idsKey = habituales.map((h) => h.unified_id).join(",");
  const excludedKey = unavailableStores.join(",");

  useEffect(() => {
    if (!idsKey) {
      setState({ products: EMPTY, missing: EMPTY, loading: false });
      return;
    }

    const ids = idsKey.split(",");
    const excluded = excludedKey ? excludedKey.split(",") : [];
    let cancelled = false;
    setState((prev) => ({ ...prev, loading: true }));

    getProductsByIds(ids)
      .then((data) => {
        if (cancelled) return;
        // `missing` se calcula contra la respuesta CRUDA, antes de recortar por
        // cobertura. Al revés, un habitual que sólo vende una tienda que no
        // entrega en esta dirección se reportaría como "ya no se vende", que es
        // mentira — y es la misma clase de error que useUnavailableCartItems
        // documenta evitando marcar los ausentes de /price-preview.
        const devueltos = new Set(data.map((p) => p.unified_id));
        const missing = ids.filter((id) => !devueltos.has(id));

        setState({
          products: stripUnavailableStores(data, excluded),
          missing: missing.length > 0 ? missing : EMPTY,
          loading: false,
        });
      })
      .catch(() => {
        if (cancelled) return;
        // Visible para quien desarrolla, invisible para el usuario: sin esto, una
        // sección que se esconde sola cuando falla es indistinguible de un usuario
        // nuevo, y puede quedar muerta una semana sin que nadie lo note.
        console.warn("[SmartCart] No se pudieron resolver los productos habituales.");
        setState({ products: EMPTY, missing: EMPTY, loading: false });
      });

    return () => {
      cancelled = true;
    };
  }, [idsKey, excludedKey]);

  return state;
}
