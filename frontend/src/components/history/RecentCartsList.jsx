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
 */
export function RecentCartsList() {
  const { recentCarts } = useHistory();
  const listados = recentCarts.slice(0, CARRITOS_LISTADOS);

  if (listados.length === 0) return null;

  return (
    <div>
      <div className="mb-1 flex items-start justify-between gap-3">
        <h2 className="font-display text-lg font-bold text-ink">Tus últimas compras</h2>
        <ClearHistoryButton />
      </div>
      <ul className="divide-y divide-line">
        {listados.map((entry) => (
          <RecentCartCard key={entry.id} entry={entry} />
        ))}
      </ul>
    </div>
  );
}
