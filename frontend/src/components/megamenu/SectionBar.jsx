import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useShelves } from "../../hooks/useShelves";
import { getSectionIcon } from "./sectionIcons";
import { MegaMenuPanel } from "./MegaMenuPanel";

/**
 * Las secciones del catálogo como fila de botones bajo el header, estilo Coto.
 *
 * Reemplaza al botón "Categorías" que abría un modal: los usuarios no lo
 * encontraban y no sabían por dónde empezar. Acá las secciones están a la vista
 * en todas las páginas, con marco para que se lean como botones.
 *
 * Con mouse, pasar por encima despliega las góndolas; en un touchscreen no hay
 * hover, así que el tap hace lo mismo. Se cierra al salir con el mouse, al
 * tocar afuera, con Escape o al elegir una góndola.
 */
export function SectionBar() {
  const { sections } = useShelves();
  const [activeSection, setActiveSection] = useState(null);
  const navRef = useRef(null);

  useEffect(() => {
    if (!activeSection) return;
    function handleKeyDown(event) {
      if (event.key === "Escape") setActiveSection(null);
    }
    function handlePointerDown(event) {
      if (!navRef.current.contains(event.target)) setActiveSection(null);
    }
    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("pointerdown", handlePointerDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [activeSection]);

  if (sections.length === 0) return null;

  const activeNode = sections.find((node) => node.section === activeSection) || null;

  return (
    <nav
      ref={navRef}
      aria-label="Categorías"
      onMouseLeave={() => setActiveSection(null)}
      className="relative border-b border-line bg-surface"
    >
      {/* Las secciones vienen en el orden de src/shelves.py, que es deliberado.
          En pantalla chica no entran las nueve: la fila scrollea de costado. */}
      <ul className="mx-auto flex max-w-7xl gap-2 overflow-x-auto px-4 py-2 [scrollbar-width:none]">
        {sections.map((node) => {
          const Icon = getSectionIcon(node.section);
          const isActive = node.section === activeSection;
          return (
            <li key={node.section} className="shrink-0">
              <button
                type="button"
                aria-expanded={isActive}
                onMouseEnter={() => setActiveSection(node.section)}
                onClick={() => setActiveSection(node.section)}
                className={`flex items-center gap-1.5 whitespace-nowrap rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "border-brand-violet-500 bg-brand-violet-100 text-brand-violet-700"
                    : "border-line text-ink"
                }`}
              >
                <Icon size={16} className="shrink-0" aria-hidden="true" />
                {node.section}
                <ChevronDown size={14} className="shrink-0" aria-hidden="true" />
              </button>
            </li>
          );
        })}
      </ul>

      {activeNode && (
        <div className="absolute inset-x-0 top-full px-4">
          <div className="mx-auto flex max-h-[70vh] max-w-7xl overflow-hidden rounded-b-lg border border-t-0 border-line shadow-xl">
            <MegaMenuPanel section={activeNode} onNavigate={() => setActiveSection(null)} />
          </div>
        </div>
      )}
    </nav>
  );
}
