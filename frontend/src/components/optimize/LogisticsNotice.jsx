import { AlertTriangle } from "lucide-react";
import { STORES } from "../../utils/constants";

/**
 * Avisa qué tiendas quedaron fuera porque no entregan en la dirección, sólo
 * cuando es novedad: las que ya se sabía (`knownUncovered`, el estado del
 * perfil al pedir la optimización) se avisaron antes y la grilla ya las saca.
 *
 * Sin esto, que una tienda no aparezca en el split es indistinguible de que haya
 * salido cara, y el usuario no tiene forma de saber que el motivo es que no le
 * entregan. El envío estimado (`source: "fallback"`) ya no es un cartel: se
 * marca "(estimado)" al lado del envío en la tarjeta de la tienda, que es donde
 * está el número que describe.
 */
export function LogisticsNotice({ result, knownUncovered = [] }) {
  const excludedStores = result.excluded_stores || [];
  const uncovered = STORES.filter(({ key, id }) => {
    const logistics = result.logistics?.[key];
    return (
      logistics && !knownUncovered.includes(id) && (excludedStores.includes(id) || logistics.covered === false)
    );
  });

  return uncovered.map(({ key, name }) => (
    <div key={key} className="flex items-start gap-2 rounded-lg border border-state-warning/40 bg-state-warning/10 p-4">
      <AlertTriangle size={18} className="mt-0.5 shrink-0 text-state-warning" />
      <div className="text-sm">
        <p className="font-semibold text-ink">{name} quedó fuera de la comparación</p>
        <p className="mt-1 text-ink-muted">
          {result.logistics[key].message || `${name} no realiza entregas en tu dirección.`}
        </p>
      </div>
    </div>
  ));
}
