import { Link } from "react-router-dom";

/**
 * Las góndolas de una sección.
 *
 * Ya no hay regla de ruteo que decidir: toda góndola resuelve por
 * `/categoria/{slug}` y toda góndola tiene productos, porque la lista sale de la
 * misma tabla que decide qué se scrapea (`src/shelves.py`). Antes el destino
 * dependía de `has_direct_category_match`, y el caso mayoritario —el `false`—
 * mandaba a una búsqueda semántica por el nombre de la categoría, que sobre un
 * catálogo de 20 góndolas devolvía cualquier cosa.
 */
export function MegaMenuPanel({ section, onNavigate }) {
  if (!section) return null;

  return (
    <div className="flex-1 overflow-y-auto bg-surface p-6">
      <p className="mb-4 font-display text-sm font-semibold text-brand-accent">
        {section.section.toUpperCase()}
      </p>

      {section.shelves.length === 0 ? (
        <p className="text-sm text-ink-muted">Sin góndolas cargadas todavía.</p>
      ) : (
        <div className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
          {section.shelves.map((shelf) => (
            <Link
              key={shelf.slug}
              to={`/categoria/${shelf.slug}`}
              onClick={onNavigate}
              className="text-left text-sm text-ink-muted hover:text-brand-violet-700 hover:underline"
            >
              {shelf.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
