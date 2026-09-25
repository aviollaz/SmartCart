import { useProfile } from "../../context/ProfileContext";
import { AddressField } from "./AddressField";
import { MultiSelectField } from "./MultiSelectField";
import { CARD_OPTIONS, MEMBERSHIP_OPTIONS } from "../../utils/paymentOptions";

// Reemplaza el sidebar fijo de Streamlit ("Tu Perfil"): vive inline en
// /carrito, justo antes de optimizar, ya que estos datos solo se consumen
// al llamar a POST /optimize (no durante la navegaciÃ³n/bÃºsqueda).
export function ProfileDrawer({ onOpenLocation }) {
  const { cards, memberships, setCards, setMemberships } = useProfile();

  return (
    <section className="rounded-lg border border-line bg-surface p-5">
      <h2 className="mb-4 font-display text-lg font-bold text-ink">Tu perfil</h2>
      <div className="flex flex-col gap-4">
        <AddressField onOpenLocation={onOpenLocation} />
        <MultiSelectField label="Tarjetas bancarias" options={CARD_OPTIONS} selected={cards} onChange={setCards} />
        <MultiSelectField
          label="MembresÃ­as de supermercados"
          options={MEMBERSHIP_OPTIONS}
          selected={memberships}
          onChange={setMemberships}
        />
      </div>
    </section>
  );
}
