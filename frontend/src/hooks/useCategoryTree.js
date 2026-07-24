import { useEffect, useState } from "react";
import { getCategoryTree } from "../api/categories";

let cachedTreePromise = null;

/** El árbol de categorías es estático por sesión de backend: se fetchea una
 * sola vez y se comparte entre todos los componentes que lo usen (mega-menú,
 * y potencialmente otras pantallas), evitando refetches en cada apertura. */
export function useCategoryTree() {
  const [tree, setTree] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    if (!cachedTreePromise) {
      cachedTreePromise = getCategoryTree();
    }
    cachedTreePromise
      .then((data) => {
        if (!cancelled) setTree(data);
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

  return { tree, loading, error };
}
