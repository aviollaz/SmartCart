import { useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react";

// Regla de ruteo (ver src/category_tree.py / docs/smartcart_spec.md §2.1):
// un top-level con has_direct_category_match=True resuelve vía
// /categoria/{label} (match exacto en unified_products.category); cualquier
// otro click (subcategoría, leaf, o top-level sin match directo) resuelve
// vía /buscar?q=<label> (búsqueda semántica).
function buildHref(label, hasDirectCategoryMatch) {
  if (hasDirectCategoryMatch) return `/categoria/${encodeURIComponent(label)}`;
  return `/buscar?q=${encodeURIComponent(label)}`;
}

export function MegaMenuPanel({ topNode, onNavigate }) {
  const navigate = useNavigate();

  if (!topNode) return null;

  const subcategories = Object.values(topNode.subcategories).sort((a, b) =>
    a.label.localeCompare(b.label, "es")
  );

  function go(label, hasDirectCategoryMatch = false) {
    navigate(buildHref(label, hasDirectCategoryMatch));
    onNavigate();
  }

  return (
    <div className="flex-1 overflow-y-auto bg-surface p-6">
      <button
        type="button"
        onClick={() => go(topNode.label, topNode.has_direct_category_match)}
        className="mb-4 flex items-center gap-1 font-display text-sm font-semibold text-brand-accent hover:underline"
      >
        VER TODOS LOS PRODUCTOS DE {topNode.label.toUpperCase()}
        <ChevronRight size={16} aria-hidden="true" />
      </button>

      {subcategories.length === 0 ? (
        <p className="text-sm text-ink-muted">Sin subcategorías cargadas todavía.</p>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {subcategories.map((sub) => (
            <div key={sub.label}>
              <button
                type="button"
                onClick={() => go(sub.label)}
                className="mb-2 text-left font-display text-sm font-semibold text-brand-violet-700 hover:underline"
              >
                {sub.label}
              </button>
              <ul className="space-y-1.5">
                {sub.leaves.length === 0 ? (
                  <li className="text-sm text-ink-muted">Ver todo</li>
                ) : (
                  sub.leaves.map((leaf) => (
                    <li key={leaf}>
                      <button
                        type="button"
                        onClick={() => go(leaf)}
                        className="text-left text-sm text-ink-muted hover:text-brand-violet-700 hover:underline"
                      >
                        {leaf}
                      </button>
                    </li>
                  ))
                )}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
