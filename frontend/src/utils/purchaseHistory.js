/**
 * Historial de compras: transformaciones puras sobre lo que se guarda en
 * localStorage.
 *
 * Viven acá y no adentro de HistoryContext por el mismo motivo que
 * cartOperations.js: son la parte donde un error no se ve —queda un producto de
 * más en el ranking, o una compra contada dos veces— en vez de romper la
 * pantalla.
 */

/**
 * La clave lleva `_v1` por simetría con `smartcart_cart_v1` y
 * `smartcart_profile_v1`, pero **NO se bumpea nunca**.
 *
 * La regla ya existía (ProfileContext: la clave no se versiona, la migración es
 * un efecto con spread), pero acá es más fuerte que una convención. Que el
 * carrito pierda su contenido le cuesta al usuario cinco minutos de volver a
 * elegir; que el historial pierda el suyo le cuesta meses de señal que **ninguna
 * acción del usuario puede reconstruir**: no hay copia en el servidor, no hay
 * login y no hay tabla por usuario. Agregar un campo a la entrada se resuelve
 * tolerándolo ausente en normalizeHistory(), no cambiando la clave.
 */
export const HISTORY_STORAGE_KEY = "smartcart_history_v1";

/**
 * Tope de carritos guardados.
 *
 * Veinte carritos semanales son ~5 meses de señal, bastante más de lo que un
 * ranking por frecuencia aprovecha (la recompra de supermercado la domina lo
 * reciente). En tamaño son ~50 KB, cómodos dentro de la cuota del origen.
 *
 * Pero el tope no es sólo por tamaño: protege a las OTRAS dos claves. La
 * escritura de useLocalStorage es un try/catch que se traga el error, así que un
 * historial sin techo que termine reventando la cuota compartida haría que el
 * carrito deje de persistir en silencio y sin error en ningún lado. Por eso el
 * recorte vive en recordPurchase() y no en la UI: el invariante tiene que ser
 * imposible de saltear.
 */
export const MAX_ENTRIES = 20;

/**
 * Ventana dentro de la cual dos optimizaciones son la MISMA compra.
 *
 * Es la decisión no obvia de toda la feature. Una sola sesión de compra pega
 * varias veces contra /optimize: aceptar una sugerencia re-optimiza sola (el
 * reoptimizeRef de CartPage), aplicar un cierre de tienda también, deshacer
 * también, y "cambio una cantidad y vuelvo a optimizar" es el flujo normal.
 * Anexar una entrada por corrida no es sólo ruidoso: está sesgado en una
 * dirección concreta, porque sobrepondera justo los carritos que el usuario más
 * manoseó. Una tarde de indecisión le gana para siempre a tres meses de compras.
 *
 * SmartCart además no tiene checkout —el usuario se va al sitio de la cadena—,
 * así que **no existe ninguna acción que signifique "ya está, compré"**. El
 * tiempo es la única señal disponible.
 *
 * El error es asimétrico y por eso la ventana es corta: quedarse corto parte una
 * sesión en dos entradas (el ranking cuenta doble una vez, y aparece una fila
 * repetida en la lista: molesto, acotado y VISIBLE), mientras que pasarse une dos
 * compras genuinamente distintas y **destruye la primera**, en silencio y sin
 * vuelta atrás. Media hora es órdenes de magnitud más que cualquier ciclo de
 * swap-y-reintento, y bastante menos que una segunda salida el mismo día.
 */
export const SESSION_WINDOW_MS = 30 * 60 * 1000;

export const EMPTY_HISTORY = Object.freeze({ entries: [] });

/**
 * Lectura tolerante de lo que haya en localStorage.
 *
 * Es lo que hace segura la promesa de no versionar la clave: acepta null, un
 * array pelado, un `entries` ausente o que no sea array, y descarta entradas sin
 * `items`. Todo campo que se agregue en el futuro se tolera ausente acá.
 */
export function normalizeHistory(stored) {
  const raw = Array.isArray(stored) ? stored : stored?.entries;
  if (!Array.isArray(raw)) return EMPTY_HISTORY;

  const entries = raw
    .filter((entry) => entry && typeof entry.items === "object" && entry.items !== null)
    .map((entry) => ({
      id: entry.id || String(entry.at || 0),
      at: typeof entry.at === "number" ? entry.at : 0,
      items: entry.items,
      total: typeof entry.total === "number" ? entry.total : null,
      stores: Array.isArray(entry.stores) ? entry.stores : [],
    }));

  return { entries };
}

/**
 * Registra una compra optimizada. Devuelve un historial nuevo, más nuevo primero.
 *
 * Si la entrada más reciente cae dentro de SESSION_WINDOW_MS, se REEMPLAZA en
 * lugar de anexar: la última corrida es la que más se parece a lo que el usuario
 * efectivamente compró, porque ya incluye los swaps que aceptó. Las intermedias
 * describen carritos que miró y descartó.
 *
 * Vale dejarlo dicho: optimizar no es comprar. Esto mide intención de compra, y
 * la regla de sesión es lo que la acerca a una compra.
 */
export function recordPurchase(history, { items, total = null, stores = [], at = Date.now() }) {
  const normalized = normalizeHistory(history);
  if (!items || Object.keys(items).length === 0) return normalized;

  const entry = { id: String(at), at, items, total, stores };
  const [newest] = normalized.entries;
  const sameSession = newest && at - newest.at < SESSION_WINDOW_MS;

  const entries = sameSession
    ? [{ ...entry, id: newest.id }, ...normalized.entries.slice(1)]
    : [entry, ...normalized.entries];

  return { entries: entries.slice(0, MAX_ENTRIES) };
}

/**
 * Ranking de "mis habituales": los productos que más veces aparecieron.
 *
 * Se ordena por CANTIDAD DE COMPRAS, no por unidades sumadas: llevar 6 yogures
 * una vez no es un hábito, llevar 1 en 6 viajes sí. `totalQuantity` se calcula
 * igual porque sale gratis y es lo que necesitaría un futuro "repetir con la
 * cantidad de siempre".
 *
 * `minPurchases = 2` deja afuera lo comprado una sola vez, que no es un hábito
 * sino el último carrito — y ese ya lo muestra "Tus últimas compras". La
 * consecuencia (con una sola compra el ranking sale vacío) se maneja escondiendo
 * la sección, NO bajando el umbral para llenar la grilla.
 */
export function selectHabituales(history, { limit = 12, minPurchases = 2 } = {}) {
  const { entries } = normalizeHistory(history);
  const byUid = new Map();

  // Las entradas vienen más nuevas primero, así que el primer nombre que se ve
  // de cada producto es el más fresco.
  for (const entry of entries) {
    for (const [unifiedId, item] of Object.entries(entry.items)) {
      const acc = byUid.get(unifiedId);
      if (acc) {
        acc.purchases += 1;
        acc.totalQuantity += item?.quantity || 0;
      } else {
        byUid.set(unifiedId, {
          unified_id: unifiedId,
          name: item?.name || unifiedId,
          purchases: 1,
          totalQuantity: item?.quantity || 0,
          lastAt: entry.at,
        });
      }
    }
  }

  return [...byUid.values()]
    .filter((h) => h.purchases >= minPurchases)
    // El desempate por nombre no es cosmético: sin un orden total, la grilla se
    // reordena sola entre renders sin que haya cambiado nada.
    .sort((a, b) => b.purchases - a.purchases || b.lastAt - a.lastAt || a.name.localeCompare(b.name))
    .slice(0, limit);
}

/** Los últimos carritos, ya normalizados, para la lista de "Tus últimas compras". */
export function selectRecentCarts(history, limit = 5) {
  return normalizeHistory(history).entries.slice(0, limit);
}
