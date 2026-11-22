// Ordenamientos de la comparación por súper (/compare).
//
// Los dos de precio usan el precio para comparar (`comparable_total`): lo que
// a un súper le falta ya suma lo que cuesta en el más caro de los otros, así
// que no premia al que menos tiene. Un súper sin total va siempre al final.

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

/** El precio para comparar más bajo de la semana: el de otro día si lo hay, si no el de hoy. */
function bestDayTotal(store) {
  return store.best_day?.comparable_total ?? store.comparable_total;
}

const byPrice = (price) => (a, b) =>
  (a.total == null) - (b.total == null) ||
  (price(a) ?? 0) - (price(b) ?? 0);

// Fiel = lo que se compra se parece más a lo elegido: primero el que menos
// productos deja sin comprar, después el que más tiene igual (menos
// reemplazos), y a igualdad el más barato hoy.
const byFidelity = (a, b) =>
  a.missing - b.missing ||
  b.exact - a.exact ||
  (a.total == null) - (b.total == null) ||
  (a.comparable_total ?? 0) - (b.comparable_total ?? 0);

const COMPARATORS = {
  [COMPARE_SORTS.PRICE_TODAY]: byPrice((s) => s.comparable_total),
  [COMPARE_SORTS.PRICE_BEST_DAY]: byPrice(bestDayTotal),
  [COMPARE_SORTS.FIDELITY]: byFidelity,
};

export function sortStores(stores, sortBy) {
  const compare = COMPARATORS[sortBy] ?? COMPARATORS[COMPARE_SORTS.PRICE_TODAY];
  // Desempate estable por store_id, para que el orden no salte entre recálculos.
  return [...stores].sort((a, b) => compare(a, b) || String(a.store_id).localeCompare(String(b.store_id)));
}
