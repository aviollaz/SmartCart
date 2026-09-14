import { AlertTriangle, Truck } from "lucide-react";

/**
 * Explica de dónde salió el envío usado en la optimización, sólo cuando hay
 * algo accionable que decir.
 *
 * Sin esto, que Coto no aparezca en el split es indistinguible de que Coto haya
 * salido cara, y el usuario no tiene forma de saber que el motivo es que no le
 * entregan. El caso "fallback" también se muestra: un costo estimado presentado
 * como si fuera el real es peor que un costo estimado declarado como tal. El
 * caso "todo normal" no se muestra: el desglose por tienda ya deja ver qué
 * tiendas participan, y confirmar eso de nuevo acá es ruido.
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

  if (coto.source === "fallback") {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-line bg-surface p-4">
        <Truck size={18} className="mt-0.5 shrink-0 text-ink-muted" />
        <p className="text-sm text-ink-muted">
          El envío de Coto es una <strong>estimación por zona</strong>: no pudimos consultar la
          tarifa real en este momento.
        </p>
      </div>
    );
  }

  // Coto entrega y el envío es el tarifado real: no hay nada accionable que
  // decir que el desglose por tienda no muestre ya, así que no se dibuja
  // nada. Antes esta rama confirmaba "todo normal" con su propia tarjeta,
  // pero eso es ruido al lado de las dos únicas ramas que sí importan.
  return null;
}
