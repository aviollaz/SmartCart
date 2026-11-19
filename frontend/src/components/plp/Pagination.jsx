import { ChevronLeft, ChevronRight } from "lucide-react";

// Cuántas páginas se muestran a cada lado de la actual.
const SIDE = 3;

/**
 * Flechas para anterior/siguiente y hasta SIDE páginas a cada lado de la
 * actual, para saltar directo. Va arriba y abajo de la grilla: cambiar de
 * página sube al principio, y así se sigue pasando sin bajar de nuevo.
 */
export function Pagination({ page, totalPages, onChange, className = "" }) {
  if (totalPages <= 1) return null;
  const first = Math.max(1, page - SIDE);
  const last = Math.min(totalPages, page + SIDE);
  const pages = Array.from({ length: last - first + 1 }, (_, i) => first + i);
  const base = "flex h-8 min-w-8 items-center justify-center rounded-md border px-2 text-sm";

  return (
    <nav aria-label="Páginas" className={`flex items-center justify-center gap-1 ${className}`}>
      <button
        type="button"
        onClick={() => onChange(page - 1)}
        disabled={page <= 1}
        aria-label="Página anterior"
        className={`${base} border-line text-ink hover:bg-surface-muted disabled:opacity-40`}
      >
        <ChevronLeft size={16} />
      </button>
      {pages.map((n) => (
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
      ))}
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
