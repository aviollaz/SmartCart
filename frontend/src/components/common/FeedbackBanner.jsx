import { MessageSquare } from "lucide-react";
import { FEEDBACK_FORM_URL } from "../../utils/constants";

/** El cartel que lleva al formulario de feedback (FAQ y comparación). */
export function FeedbackBanner({ className = "" }) {
  if (!FEEDBACK_FORM_URL) return null;
  return (
    <div className={`flex flex-wrap items-center justify-between gap-4 rounded-lg border border-brand-violet-100 bg-brand-violet-100 p-5 ${className}`}>
      <p className="flex items-center gap-2 text-sm text-ink">
        <MessageSquare size={18} className="shrink-0 text-brand-violet-700" aria-hidden="true" />
        ¿Algo no anda o tenés una idea? Nos ayuda mucho saberlo.
      </p>
      <a
        href={FEEDBACK_FORM_URL}
        target="_blank"
        rel="noreferrer"
        className="rounded-md bg-brand-accent px-4 py-2 text-sm font-semibold text-white hover:bg-brand-accent-dark"
      >
        Contanos
      </a>
    </div>
  );
}
