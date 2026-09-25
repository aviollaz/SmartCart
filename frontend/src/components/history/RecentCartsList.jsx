import { ChevronDown } from "lucide-react";
import { useHistory } from "../../context/HistoryContext";
import { ClearHistoryButton } from "./ClearHistoryButton";
import { RecentCartCard } from "./RecentCartCard";

const CARRITOS_LISTADOS = 3;

/**
 * "Tus últimas compras": los carritos optimizados más recientes.
 *
 * El botón de borrar vive acá y no en la grilla de habituales porque es acá donde
 * el historial se ve como lo que es —una lista de compras guardadas—, así que es
 * donde el usuario va a buscarlo. Mismo lugar relativo que ClearCartButton en el
 * encabezado de "Productos seleccionados".
 *
 * Va plegada: es la parte menos usada del historial y la que más texto tiene,
 * y abierta empujaba el resto de la home hacia abajo. El resumen dice cuántas
 * hay, así que sigue siendo evidente que existe.
 */
export function RecentCartsList() {
  const { recentCarts } = useHistory();
  const listados = recentCarts.slice(0, CARRITOS_LISTADOS);

  if (listados.length === 0) return null;

  return (
    <details className="group rounded-md border border-line">
      <summary className="flex cursor-pointer select-none items-center justify-between gap-3 px-4 py-3">
        <span className="font-display text-base font-bold text-ink">
          Repetir una compra anterior ({listados.length})
        </span>
        <ChevronDown size={18} className="shrink-0 text-ink-muted transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t border-line px-4 pb-2">
        <div className="flex justify-end pt-2">
          <ClearHistoryButton />
        </div>
        <ul className="divide-y divide-line">
          {listados.map((entry) => (
            <RecentCartCard key={entry.id} entry={entry} />
          ))}
        </ul>
      </div>
    </details>
  );
}
