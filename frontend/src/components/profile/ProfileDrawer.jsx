import { useProfile } from "../../context/ProfileContext";
import { AddressField } from "./AddressField";
import { MultiSelectField } from "./MultiSelectField";

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
// Se copian y no se exponen por un endpoint: son 27 strings que cambian
// cuando cambia la lista de entidades, o sea en el mismo commit que ya
// obliga a tocar los dos archivos.
const CARD_OPTIONS = [
  { value: "galicia", label: "Galicia" },
  { value: "macro", label: "Macro" },
  { value: "nacion", label: "Nación" },
  { value: "bbva", label: "BBVA" },
  { value: "santander", label: "Santander" },
  { value: "icbc", label: "ICBC" },
  { value: "hsbc", label: "HSBC" },
  { value: "itau", label: "Itaú" },
  { value: "provincia", label: "Provincia" },
  { value: "hipotecario", label: "Hipotecario" },
  { value: "ciudad", label: "Ciudad" },
  { value: "comafi", label: "Comafi" },
  { value: "credicoop", label: "Credicoop" },
  { value: "patagonia", label: "Patagonia" },
  { value: "supervielle", label: "Supervielle" },
  { value: "columbia", label: "Columbia" },
  { value: "banco_del_sol", label: "Banco del Sol" },
  { value: "carrefour_banco", label: "Carrefour Banco" },
  { value: "naranja_x", label: "Naranja X" },
  { value: "amex", label: "American Express" },
  { value: "cabal", label: "Cabal" },
  { value: "mercado_pago", label: "Mercado Pago" },
  { value: "modo", label: "MODO" },
  { value: "uala", label: "Ualá" },
  { value: "prex", label: "Prex" },
  { value: "personal_pay", label: "Personal Pay" },
];
// "mi_carrefour" no es decorativo: en Carrefour el precio rebajado suele ser el
// del programa de fidelidad ("Doble Precio"), y sin declararlo el optimizador
// cotiza a precio de lista a propósito, para no prometer un precio de socio.
// Mismo criterio que CARD_OPTIONS, pero contra el otro eje: el loader marca
// estas entidades con `is_membership` y el optimizador las busca en
// user_memberships (ver MEMBERSHIP_ENTITIES en src/promotions/banks.py).
//
// "jumbo_mas" se fue: Jumbo no es una de las tres cadenas del proyecto, así
// que era una opción que no podía aplicar a ningún precio — ruido que invita
// a preguntar por una tienda que no existe acá.
const MEMBERSHIP_OPTIONS = [
  { value: "club_dia", label: "Club Día" },
  { value: "coto_tci", label: "Coto TCI" },
  { value: "comunidad_coto", label: "Comunidad Coto" },
  { value: "mi_carrefour", label: "Mi Carrefour" },
  { value: "club_la_nacion", label: "Club La Nación" },
];

// Reemplaza el sidebar fijo de Streamlit ("Tu Perfil"): vive inline en
// /carrito, justo antes de optimizar, ya que estos datos solo se consumen
// al llamar a POST /optimize (no durante la navegación/búsqueda).
export function ProfileDrawer({ onOpenLocation }) {
  const { cards, memberships, setCards, setMemberships } = useProfile();

  return (
    <section className="rounded-lg border border-line bg-surface p-5">
      <h2 className="mb-4 font-display text-lg font-bold text-ink">Tu perfil</h2>
      <div className="flex flex-col gap-4">
        <AddressField onOpenLocation={onOpenLocation} />
        <MultiSelectField label="Tarjetas bancarias" options={CARD_OPTIONS} selected={cards} onChange={setCards} />
        <MultiSelectField
          label="Membresías de supermercados"
          options={MEMBERSHIP_OPTIONS}
          selected={memberships}
          onChange={setMemberships}
        />
      </div>
    </section>
  );
}
