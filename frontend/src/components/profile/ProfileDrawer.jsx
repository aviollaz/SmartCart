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
const CARD_OPTIONS = [
  "galicia",
  "macro",
  "nacion",
  "bbva",
  "santander",
  "icbc",
  "ciudad",
  "comafi",
  "credicoop",
  "patagonia",
  "supervielle",
  "columbia",
  "banco_del_sol",
  "carrefour_banco",
  "naranja_x",
  "amex",
  "cabal",
  "mercado_pago",
  "modo",
  "uala",
  "prex",
  "personal_pay",
];
// "mi_carrefour" no es decorativo: en Carrefour el precio rebajado suele ser el
// del programa de fidelidad ("Doble Precio"), y sin declararlo el optimizador
// cotiza a precio de lista a propósito, para no prometer un precio de socio.
// Mismo criterio que CARD_OPTIONS, pero contra el otro eje: el loader marca
// estas entidades con `is_membership` y el optimizador las busca en
// user_memberships (ver MEMBERSHIP_ENTITIES en src/promotions/banks.py).
const MEMBERSHIP_OPTIONS = [
  "club_dia",
  "coto_tci",
  "comunidad_coto",
  "jumbo_mas",
  "mi_carrefour",
  "club_la_nacion",
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
