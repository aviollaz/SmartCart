// Ordenamientos de la comparación por súper (/compare).
//
// Los dos de precio ponen primero a los súper que tienen todo: el total de un
// súper con faltantes no incluye esos productos, y ordenarlo crudo premiaría
// al que menos tiene (la misma razón por la que /compare reemplaza en vez de
// omitir). Un súper sin total (no se pudo cotizar) va siempre al final.

export const COMPARE_SORTS = {
  PRICE_TODAY: "precio_hoy",
  PRICE_BEST_DAY: "precio_mejor_dia",
  FIDELITY: "fidelidad",
};

export const COMPARE_SORT_LABELS = {
  [COMPARE_SORTS.PRICE_TODAY]: "Precio hoy",
  [COMPARE_SORTS.PRICE_BEST_DAY]: "Precio el día más barato",
  [COMPARE_SORTS.FIDELITY]: "Más fiel a tu compra",
};

/** El total más bajo de la semana: el de otro día si lo hay, si no el de hoy. */
export function bestDayTotal(store) {
  return store.best_day?.total ?? store.total;
}

const byPrice = (price) => (a, b) =>
  (a.total == null) - (b.total == null) ||
  (a.missing > 0) - (b.missing > 0) ||
  (price(a) ?? 0) - (price(b) ?? 0);

// Fiel = lo que se compra se parece más a lo elegido: primero el que menos
// productos deja sin comprar, después el que más tiene igual (menos
// reemplazos), y a igualdad el más barato hoy.
const byFidelity = (a, b) =>
  a.missing - b.missing ||
  b.exact - a.exact ||
  (a.total == null) - (b.total == null) ||
  (a.total ?? 0) - (b.total ?? 0);

const COMPARATORS = {
  [COMPARE_SORTS.PRICE_TODAY]: byPrice((s) => s.total),
  [COMPARE_SORTS.PRICE_BEST_DAY]: byPrice(bestDayTotal),
  [COMPARE_SORTS.FIDELITY]: byFidelity,
};

export function sortStores(stores, sortBy) {
  const compare = COMPARATORS[sortBy] ?? COMPARATORS[COMPARE_SORTS.PRICE_TODAY];
  // Desempate estable por store_id, para que el orden no salte entre recálculos.
  return [...stores].sort((a, b) => compare(a, b) || String(a.store_id).localeCompare(String(b.store_id)));
}
