import { useProfile } from "../../context/ProfileContext";
import { AddressField } from "./AddressField";
import { MultiSelectField } from "./MultiSelectField";

const CARD_OPTIONS = ["galicia", "macro", "nacion", "bbva", "mercado_pago"];
// "mi_carrefour" no es decorativo: en Carrefour el precio rebajado suele ser el
// del programa de fidelidad ("Doble Precio"), y sin declararlo el optimizador
// cotiza a precio de lista a propósito, para no prometer un precio de socio.
const MEMBERSHIP_OPTIONS = ["club_dia", "coto_tci", "comunidad_coto", "jumbo_mas", "mi_carrefour"];

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
