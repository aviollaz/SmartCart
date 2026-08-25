import { useNavigate } from "react-router-dom";
import { RotateCcw } from "lucide-react";
import { useCart } from "../../context/CartContext";
import { formatPrice, storeName } from "../../utils/formatters";

const FECHA = new Intl.DateTimeFormat("es-AR", { day: "numeric", month: "short" });

/**
 * Una compra pasada, con el botón para repetirla.
 *
 * El total y las tiendas se muestran SIEMPRE junto a la fecha, y con el verbo en
 * pasado ("pagaste"): son un snapshot de ese día, no el precio de hoy. Presentar
 * un total viejo como si fuera vigente rompería la promesa central de la app.
 */
export function RecentCartCard({ entry }) {
  const { items, mergeItems } = useCart();
  const navigate = useNavigate();

  const unifiedIds = Object.keys(entry.items);
  const yaEnCarrito = unifiedIds.filter((unifiedId) => items[unifiedId]).length;

  const handleRepetir = () => {
    mergeItems(entry.items);
    // En la home es el único efecto visible del click (el badge del carrito solo
    // es demasiado callado); en /carrito es un no-op y la sección se desmonta
    // igual, porque el carrito deja de estar vacío.
    navigate("/carrito");
  };

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="text-sm text-ink">
          {entry.at ? FECHA.format(new Date(entry.at)) : "Sin fecha"} ·{" "}
          {unifiedIds.length === 1 ? "1 producto" : `${unifiedIds.length} productos`}
          {typeof entry.total === "number" && <> · pagaste {formatPrice(entry.total)}</>}
        </p>
        {entry.stores.length > 0 && (
          <p className="text-xs text-ink-muted">{entry.stores.map(storeName).join(" + ")}</p>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {yaEnCarrito > 0 && (
          <span className="text-xs text-ink-muted">
            {yaEnCarrito === unifiedIds.length ? "ya está todo en tu carrito" : `${yaEnCarrito} ya en tu carrito`}
          </span>
        )}
        <button
          type="button"
          onClick={handleRepetir}
          className="flex items-center gap-1.5 rounded-md border border-brand-violet-700 px-3 py-1.5 text-xs font-semibold text-brand-violet-700 hover:bg-brand-violet-100"
        >
          <RotateCcw size={14} />
          Repetir
        </button>
      </div>
    </li>
  );
}
