import { useHistory } from "../../context/HistoryContext";
import { useHabitualProducts } from "../../hooks/useHabitualProducts";
import { ProductGrid } from "../plp/ProductGrid";

const HABITUALES_EN_GRILLA = 8;

/**
 * "Comprar de nuevo": los productos que más veces aparecieron en carritos
 * optimizados, resueltos contra el catálogo de hoy.
 *
 * Reusa ProductGrid/ProductCard tal cual en vez de dibujar una fila propia: así
 * hereda gratis el precio con promoción, la imagen, el stepper conectado al
 * carrito y el recorte por cobertura, y no hay una segunda card que pueda
 * mostrar un precio distinto al de la grilla de búsqueda.
 */
export function HabitualesGrid() {
  const { habituales, entries } = useHistory();
  const enGrilla = habituales.slice(0, HABITUALES_EN_GRILLA);
  const { products, missing, loading } = useHabitualProducts(enGrilla);

  if (enGrilla.length === 0) return null;

  // Nombre guardado en el historial: es la ÚNICA fuente para un producto que ya
  // no existe, justamente porque el endpoint no lo devuelve.
  const nombreDeMissing = (unifiedId) => {
    for (const entry of entries) {
      const item = entry.items[unifiedId];
      if (item?.name) return item.name;
    }
    return unifiedId;
  };

  return (
    <div>
      <h2 className="mb-3 font-display text-lg font-bold text-ink">Comprar de nuevo</h2>

      {loading && products.length === 0 ? (
        <p className="py-8 text-sm text-ink-muted">Buscando tus habituales…</p>
      ) : (
        <ProductGrid
          products={products}
          emptyMessage="Tus habituales no están disponibles en este momento."
        />
      )}

      {/* No se esconden ni se borran del historial: una grilla que se achica sola
          parece un bug, y el pruning es de la tienda, no del usuario — el producto
          puede volver, y el ranking no se reconstruye. */}
      {missing.length > 0 && (
        <p className="mt-3 text-xs text-ink-muted">
          {missing.length === 1 ? "Un producto que comprabas ya no está" : `${missing.length} productos que comprabas ya no están`}{" "}
          en el catálogo: {missing.map(nombreDeMissing).join(", ")}.
        </p>
      )}
    </div>
  );
}
