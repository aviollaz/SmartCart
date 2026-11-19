import { ChevronLeft, ChevronRight } from "lucide-react";

// Cuántas páginas se muestran a cada lado de la actual.
const SIDE = 2;

/**
 * ‹ [1] … [3][4][5][6][7] … [30] ›: flechas, hasta SIDE páginas a cada lado
 * de la actual, y siempre la primera y la última, así se ve cuántas hay. Va
 * arriba y abajo de la grilla: cambiar de página sube al principio, y así se
 * sigue pasando sin bajar de nuevo.
 */
export function Pagination({ page, totalPages, onChange, className = "" }) {
  if (totalPages <= 1) return null;
  const first = Math.max(1, page - SIDE);
  const last = Math.min(totalPages, page + SIDE);
  const pages = Array.from({ length: last - first + 1 }, (_, i) => first + i);
  if (first > 1) pages.unshift(...(first > 2 ? [1, "…"] : [1]));
  if (last < totalPages) pages.push(...(last < totalPages - 1 ? ["…", totalPages] : [totalPages]));
  const base = "flex h-8 min-w-7 items-center justify-center rounded-md border px-1.5 text-sm sm:min-w-8 sm:px-2";

  return (
    <nav aria-label="Páginas" className={`flex items-center justify-center gap-0.5 sm:gap-1 ${className}`}>
      <button
        type="button"
        onClick={() => onChange(page - 1)}
        disabled={page <= 1}
        aria-label="Página anterior"
        className={`${base} border-line text-ink hover:bg-surface-muted disabled:opacity-40`}
      >
        <ChevronLeft size={16} />
      </button>
      {pages.map((n, i) =>
        n === "…" ? (
          <span key={`gap${i}`} aria-hidden="true" className="px-0.5 text-sm text-ink-muted">
            …
          </span>
        ) : (
          <button
            key={n}
            type="button"
            onClick={() => onChange(n)}
            aria-current={n === page ? "page" : undefined}
            className={`${base} ${
              n === page
                ? "border-brand-violet-700 bg-brand-violet-700 font-semibold text-white"
                : "border-line text-ink hover:bg-surface-muted"
            }`}
          >
            {n}
          </button>
        )
      )}
      <button
        type="button"
        onClick={() => onChange(page + 1)}
        disabled={page >= totalPages}
        aria-label="Página siguiente"
        className={`${base} border-line text-ink hover:bg-surface-muted disabled:opacity-40`}
      >
        <ChevronRight size={16} />
      </button>
    </nav>
  );
}
