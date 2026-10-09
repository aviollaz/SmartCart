import { AlertTriangle } from "lucide-react";

/**
 * Avisa que Coto quedó fuera porque no entrega en la dirección.
 *
 * Sin esto, que Coto no aparezca en el split es indistinguible de que Coto haya
 * salido cara, y el usuario no tiene forma de saber que el motivo es que no le
 * entregan. El envío estimado (`source: "fallback"`) ya no es un cartel: se
 * marca "(estimado)" al lado del envío en la tarjeta de Coto, que es donde está
 * el número que describe.
 */
export function LogisticsNotice({ result }) {
  const coto = result.logistics?.coto;
  if (!coto) return null;

  const excluded = (result.excluded_stores || []).includes("coto_online");

  if (excluded || coto.covered === false) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-state-warning/40 bg-state-warning/10 p-4">
        <AlertTriangle size={18} className="mt-0.5 shrink-0 text-state-warning" />
        <div className="text-sm">
          <p className="font-semibold text-ink">Coto quedó fuera de la comparación</p>
          <p className="mt-1 text-ink-muted">
            {coto.message || "Coto no realiza entregas en tu dirección."}
          </p>
        </div>
      </div>
    );
  }

  return null;
}
