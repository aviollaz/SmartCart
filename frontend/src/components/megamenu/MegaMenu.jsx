import { useEffect, useRef, useState } from "react";
import { useShelves } from "../../hooks/useShelves";
import { MegaMenuRail } from "./MegaMenuRail";
import { MegaMenuPanel } from "./MegaMenuPanel";

export function MegaMenu({ open, onClose }) {
  const { sections, loading, error } = useShelves();
  const [activeSection, setActiveSection] = useState(null);
  const panelRef = useRef(null);

  // Las secciones vienen en el orden de src/shelves.py y ese orden es
  // deliberado, así que no se reordena alfabéticamente.
  useEffect(() => {
    if (open && sections.length > 0 && !activeSection) {
      setActiveSection(sections[0].section);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, sections.length]);

  useEffect(() => {
    if (!open) return;
    function handleKeyDown(event) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const activeNode = sections.find((node) => node.section === activeSection) || null;

  return (
    <div className="fixed inset-0 z-40 flex" role="dialog" aria-modal="true">
      <button
        type="button"
        aria-label="Cerrar categorías"
        onClick={onClose}
        className="absolute inset-0 bg-ink/40"
      />
      {/* Apilado en pantalla chica: el rail mide w-64 fijo, así que a 375 px le
          dejaba al panel unos 119 px y las góndolas salían cortadas. */}
      <div
        ref={panelRef}
        className="relative z-10 flex max-h-[85vh] w-full max-w-5xl translate-y-0 flex-col self-start overflow-hidden rounded-b-lg shadow-xl md:max-h-[80vh] md:flex-row"
      >
        {loading && <p className="w-full bg-surface p-6 text-sm text-ink-muted">Cargando categorías…</p>}
        {error && (
          <p className="w-full bg-surface p-6 text-sm text-state-warning">
            No pudimos cargar las categorías. Probá de nuevo más tarde.
          </p>
        )}
        {!loading && !error && (
          <>
            <MegaMenuRail
              sections={sections}
              activeSection={activeSection}
              onHover={setActiveSection}
            />
            <MegaMenuPanel section={activeNode} onNavigate={onClose} />
          </>
        )}
      </div>
    </div>
  );
}
