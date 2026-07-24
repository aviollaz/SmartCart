import { useEffect, useRef, useState } from "react";
import { useCategoryTree } from "../../hooks/useCategoryTree";
import { MegaMenuRail } from "./MegaMenuRail";
import { MegaMenuPanel } from "./MegaMenuPanel";

export function MegaMenu({ open, onClose }) {
  const { tree, loading, error } = useCategoryTree();
  const [activeLabel, setActiveLabel] = useState(null);
  const panelRef = useRef(null);

  const topLevels = tree
    ? Object.values(tree).sort((a, b) => a.label.localeCompare(b.label, "es"))
    : [];

  useEffect(() => {
    if (open && topLevels.length > 0 && !activeLabel) {
      setActiveLabel(topLevels[0].label);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, topLevels.length]);

  useEffect(() => {
    if (!open) return;
    function handleKeyDown(event) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const activeNode = topLevels.find((node) => node.label === activeLabel) || null;

  return (
    <div className="fixed inset-0 z-40 flex" role="dialog" aria-modal="true">
      <button
        type="button"
        aria-label="Cerrar categorías"
        onClick={onClose}
        className="absolute inset-0 bg-ink/40"
      />
      <div
        ref={panelRef}
        className="relative z-10 flex max-h-[80vh] w-full max-w-5xl translate-y-0 self-start overflow-hidden rounded-b-lg shadow-xl"
      >
        {loading && <p className="w-full bg-surface p-6 text-sm text-ink-muted">Cargando categorías…</p>}
        {error && (
          <p className="w-full bg-surface p-6 text-sm text-state-warning">
            No pudimos cargar las categorías. Probá de nuevo más tarde.
          </p>
        )}
        {!loading && !error && (
          <>
            <MegaMenuRail topLevels={topLevels} activeLabel={activeLabel} onHover={setActiveLabel} />
            <MegaMenuPanel topNode={activeNode} onNavigate={onClose} />
          </>
        )}
      </div>
    </div>
  );
}
