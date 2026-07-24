import { useProfile } from "../../context/ProfileContext";
import { MultiSelectField } from "./MultiSelectField";
import { ZoneSelect } from "./ZoneSelect";

const CARD_OPTIONS = ["galicia", "macro", "nacion", "bbva", "mercado_pago"];
const MEMBERSHIP_OPTIONS = ["club_dia", "coto_tci", "comunidad_coto", "jumbo_mas"];

// Reemplaza el sidebar fijo de Streamlit ("Tu Perfil"): vive inline en
// /carrito, justo antes de optimizar, ya que estos datos solo se consumen
// al llamar a POST /optimize (no durante la navegación/búsqueda).
export function ProfileDrawer() {
  const { cards, memberships, zone, setCards, setMemberships, setZone } = useProfile();

  return (
    <section className="rounded-lg border border-line bg-surface p-5">
      <h2 className="mb-4 font-display text-lg font-bold text-ink">Tu perfil</h2>
      <div className="flex flex-col gap-4">
        <MultiSelectField label="Tarjetas bancarias" options={CARD_OPTIONS} selected={cards} onChange={setCards} />
        <MultiSelectField
          label="Membresías de supermercados"
          options={MEMBERSHIP_OPTIONS}
          selected={memberships}
          onChange={setMemberships}
        />
        <ZoneSelect zone={zone} onChange={setZone} />
      </div>
    </section>
  );
}
