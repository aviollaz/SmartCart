import { useEffect, useState } from "react";
import { BadgePercent, Check, X } from "lucide-react";
import { useProfile } from "../../context/ProfileContext";
import { MEMBERSHIP_OPTIONS } from "../../utils/paymentOptions";

// A qué cadena pertenece cada programa, para que el chip se entienda sin
// saber de memoria qué es "TCI". Club La Nación no es de ninguna cadena: da
// descuentos en varias, y así se lo dice.
const MEMBERSHIP_STORE = {
  club_dia: "Día",
  coto_tci: "Coto",
  comunidad_coto: "Coto",
  mi_carrefour: "Carrefour",
  club_la_nacion: "Varias cadenas",
};

/**
 * Segundo paso del onboarding, después de la dirección: qué programas de
 * fidelidad tiene el usuario.
 *
 * Va acá y no en el carrito porque cambia lo que la grilla muestra: con Mi
 * Carrefour declarado, una sidra de $4.599 se ve a $900. Preguntarlo al final
 * dejaba al usuario armando el carrito con precios que no eran los suyos, y
 * recién el optimizador le revelaba el descuento.
 *
 * Se puede saltear ("No tengo ninguna") y se puede cambiar después desde el
 * chip "Mis clubes" del Header o desde el carrito.
 *
 * `onClose`, igual que en `LocationModal`, es lo único que distingue el
 * onboarding de la edición desde el Header. Con él, el modal se abandona sin
 * guardar (X, Escape o clic en el fondo) y "Guardar" acepta cero clubes: sacar
 * uno que se marcó por error es justo el caso para el que existe. Sin él queda
 * como paso bloqueante del onboarding. Antes la única forma de corregirlo era
 * llegar al carrito, y hasta entonces la grilla mostraba precios de socio que
 * el usuario no tenía.
 */
export function MembershipModal({ onClose }) {
  const { memberships, completeMembershipStep } = useProfile();
  const [selected, setSelected] = useState(memberships || []);
  const isEditing = Boolean(onClose);

  useEffect(() => {
    if (!onClose) return;
    function onKeyDown(event) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  function save(value) {
    completeMembershipStep(value);
    onClose?.();
  }

  function toggle(value) {
    setSelected((prev) => (prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value]));
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose ? (event) => event.target === event.currentTarget && onClose() : undefined}
    >
      <div className="w-full max-w-md rounded-lg border border-line bg-surface p-6 shadow-lg">
        <div className="mb-2 flex items-center gap-2">
          <BadgePercent className="text-brand-accent" size={20} />
          <h2 className="font-display text-lg font-bold text-ink">¿Sos socio de algún club?</h2>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Cerrar"
              className="ml-auto rounded-md p-1 text-ink-muted hover:bg-surface-muted hover:text-ink"
            >
              <X size={18} />
            </button>
          )}
        </div>
        <p className="mb-5 text-sm text-ink-muted">
          Así te mostramos los precios con tus descuentos desde el principio.
        </p>

        <ul className="mb-6 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {MEMBERSHIP_OPTIONS.map((option) => {
            const isSelected = selected.includes(option.value);
            return (
              <li key={option.value}>
                <button
                  type="button"
                  onClick={() => toggle(option.value)}
                  aria-pressed={isSelected}
                  className={`flex w-full items-center justify-between gap-2 rounded-md border px-3 py-2.5 text-left transition-colors ${
                    isSelected
                      ? "border-brand-violet-700 bg-brand-violet-100"
                      : "border-line bg-surface hover:bg-surface-muted"
                  }`}
                >
                  <span>
                    <span className="block text-sm font-semibold text-ink">{option.label}</span>
                    <span className="block text-xs text-ink-muted">{MEMBERSHIP_STORE[option.value]}</span>
                  </span>
                  <span
                    className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${
                      isSelected ? "border-brand-violet-700 bg-brand-violet-700 text-white" : "border-line"
                    }`}
                  >
                    {isSelected && <Check size={12} />}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>

        <button
          type="button"
          onClick={() => save(selected)}
          disabled={!isEditing && selected.length === 0}
          className="w-full rounded-md bg-brand-violet-700 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-violet-900 disabled:opacity-50"
        >
          {isEditing ? "Guardar" : "Listo"}
        </button>
        {!isEditing && (
          <button
            type="button"
            onClick={() => save([])}
            className="mt-3 w-full text-center text-xs text-ink-muted underline hover:text-ink"
          >
            No tengo ninguna
          </button>
        )}
      </div>
    </div>
  );
}
