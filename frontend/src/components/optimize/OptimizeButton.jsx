import { Loader2, Sparkles } from "lucide-react";

export function OptimizeButton({ onClick, disabled, loading }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || loading}
      className="flex w-full items-center justify-center gap-2 rounded-md bg-brand-accent px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-brand-accent-dark disabled:cursor-not-allowed disabled:opacity-50"
    >
      {loading ? (
        <>
          <Loader2 size={18} className="animate-spin" />
          Corriendo optimizador…
        </>
      ) : (
        <>
          <Sparkles size={18} />
          Optimizar compra
        </>
      )}
    </button>
  );
}
