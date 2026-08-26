import { useEffect, useMemo, useState } from "react";
import { getShelfSections } from "../api/categories";

let cachedSectionsPromise = null;

/**
 * Las góndolas del catálogo, agrupadas por sección.
 *
 * Son estáticas por sesión de backend (salen de `src/shelves.py`, no de la
 * base), así que se fetchean una sola vez y se comparten entre todos los
 * componentes que las usen: el mega-menú, los atajos de la home y el título de
 * la página de categoría.
 *
 * Además del array crudo devuelve `labelBySlug`, que es lo que le permite a
 * `/categoria/:shelf` mostrar "Yerba y mate" en vez del slug de la URL.
 */
export function useShelves() {
  const [sections, setSections] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    if (!cachedSectionsPromise) {
      cachedSectionsPromise = getShelfSections();
    }
    cachedSectionsPromise
      .then((data) => {
        if (!cancelled) setSections(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const shelves = useMemo(
    () => (sections || []).flatMap((section) => section.shelves),
    [sections]
  );

  const labelBySlug = useMemo(
    () => Object.fromEntries(shelves.map((shelf) => [shelf.slug, shelf.label])),
    [shelves]
  );

  return { sections: sections || [], shelves, labelBySlug, loading, error };
}
