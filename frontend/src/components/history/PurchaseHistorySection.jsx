import { useHistory } from "../../context/HistoryContext";
import { HabitualesGrid } from "./HabitualesGrid";
import { RecentCartsList } from "./RecentCartsList";

/**
 * El bloque de historial que montan la home y el carrito vacío.
 *
 * Con el historial vacío no renderiza NADA (ni un estado vacío): un usuario nuevo
 * tiene que ver la página exactamente como era antes de que esta feature
 * existiera.
 *
 * Las dos lecturas son distintas y conviven: el ranking por frecuencia
 * ("habituales") es la señal fuerte de recompra, y la lista de carritos es lo que
 * permite repetir una compra entera de un click. La grilla puede estar vacía
 * mientras la lista no lo esté — con una sola compra guardada, nada llegó todavía
 * a ser un hábito.
 */
export function PurchaseHistorySection({ className = "" }) {
  const { entries } = useHistory();
  if (entries.length === 0) return null;

  return (
    <section className={`flex flex-col gap-8 rounded-lg border border-line bg-surface p-5 ${className}`}>
      <HabitualesGrid />
      <RecentCartsList />
    </section>
  );
}
