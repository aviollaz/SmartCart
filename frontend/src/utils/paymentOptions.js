// Estos slugs tienen que coincidir con los que emite el scraper de promociones
// bancarias (BANK_ALIASES en src/promotions/banks.py): el optimizador compara
// `promo["card"] in user_cards` por igualdad exacta, así que un banco que no
// figure acá se scrapea igual pero ningún usuario puede llegar a activarlo.
// La lista sale del relevamiento real de las tres cadenas — antes tenía cinco
// entradas y dejaba afuera a ICBC, Ciudad, Patagonia, Supervielle y compañía,
// que son justamente los que más descuentos publican.
//
// El `value` es lo que viaja a /optimize y lo que tiene que coincidir con
// banks.py; el `label` es sólo lo que se dibuja. Existe porque el chip
// mostraba el slug crudo — "banco_del_sol", "naranja_x", "personal_pay" —
// y los nombres legibles ya estaban escritos del lado del backend
// (DISPLAY_NAMES en src/promotions/banks.py), sin nadie que los sirviera.
// Se copian y no se exponen por un endpoint: cambian cuando cambia la lista
// de entidades, o sea en el mismo commit que ya obliga a tocar los dos
// archivos.
//
// Sólo las que hoy tienen algún descuento en src/scrapers/bank_promos.json
// (nov-2026): Galicia, Santander, BBVA y otras sólo ofrecían cuotas, y
// tildarlas no cambiaba ningún precio. tests/test_promos.py lo verifica en los
// dos sentidos, así que regenerar el JSON puede obligar a sumar o sacar una.
export const CARD_OPTIONS = [
  { value: "icbc", label: "ICBC" },
  { value: "nacion", label: "Nación" },
  { value: "ciudad", label: "Ciudad" },
  { value: "comafi", label: "Comafi" },
  { value: "credicoop", label: "Credicoop" },
  { value: "patagonia", label: "Patagonia" },
  { value: "supervielle", label: "Supervielle" },
  { value: "columbia", label: "Columbia" },
  { value: "banco_del_sol", label: "Banco del Sol" },
  { value: "carrefour_banco", label: "Carrefour Banco" },
  { value: "naranja_x", label: "Naranja X" },
  { value: "mercado_pago", label: "Mercado Pago" },
  { value: "modo", label: "MODO" },
  { value: "personal_pay", label: "Personal Pay" },
];
// "mi_carrefour" no es decorativo: en Carrefour el precio rebajado suele ser el
// del programa de fidelidad ("Doble Precio"), y sin declararlo el optimizador
// cotiza a precio de lista a propósito, para no prometer un precio de socio.
// Mismo criterio que CARD_OPTIONS, pero contra el otro eje: el loader marca
// estas entidades con `is_membership` y el optimizador las busca en
// user_memberships (ver MEMBERSHIP_ENTITIES en src/promotions/banks.py).
//
// "cencopay" (CARD_OPTIONS) se fue en nov-2026: su 20% de Vea y Jumbo
// excluye carnes, leches y marcas propias, y no se puede aplicar al carrito
// entero. Vuelve si aparece una promo sin exclusiones en bank_promos.json.
//
// "club_dia" se fue en nov-2026: no tenía descuento bancario ni cambia el
// precio de ningún producto (el precio de socio sólo se lee en Carrefour).
//
// "jumbo_mas" se fue: no publica ningún descuento en la entidad de promos de
// Cencosud (nov 2026), así que era una opción que no podía aplicar a ningún
// precio. Vuelve si aparece en bank_promos.json.
//
// Coto TCI (la tarjeta de crédito de Coto) va al final: casi nadie la conoce,
// pero da un 20% sin tope los martes, así que sigue para quien la tiene.
export const MEMBERSHIP_OPTIONS = [
  { value: "comunidad_coto", label: "Comunidad Coto" },
  { value: "mi_carrefour", label: "Mi Carrefour" },
  { value: "club_la_nacion", label: "Club La Nación" },
  { value: "coto_tci", label: "Coto TCI" },
];
