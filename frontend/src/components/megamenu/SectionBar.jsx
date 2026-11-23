import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";
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
 * hover, así que el tap abre y un segundo tap en el mismo botón cierra. El hover
 * filtra `pointerType === "mouse"`: el tap también emite un mouseenter
 * sintético justo antes del click, que abriría el panel para que el click lo
 * cerrara. Se cierra al salir con el mouse, al tocar afuera, con Escape o al
 * elegir una góndola.
 *
 * Siempre una sola fila. Envolver en dos filas rompía el hover: bajar hacia las
 * góndolas de una sección de arriba pasaba por encima de la fila de abajo y
 * cambiaba el panel. Lo que no entra se scrollea de costado; con mouse, las
 * flechas de los bordes (sólo aparecen si hay algo de ese lado).
 */
export function SectionBar() {
  const { sections } = useShelves();
  const [activeSection, setActiveSection] = useState(null);
  const [canScroll, setCanScroll] = useState({ left: false, right: false });
  const navRef = useRef(null);
  const listRef = useRef(null);

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

  function updateScroll() {
    const list = listRef.current;
    if (!list) return;
    setCanScroll({
      left: list.scrollLeft > 0,
      right: list.scrollLeft + list.clientWidth < list.scrollWidth - 1,
    });
  }

  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    updateScroll();
    const observer = new ResizeObserver(updateScroll);
    observer.observe(list);
    return () => observer.disconnect();
  }, [sections.length]);

  function scrollList(direction) {
    const list = listRef.current;
    list.scrollBy({ left: direction * list.clientWidth * 0.6, behavior: "smooth" });
  }

  if (sections.length === 0) return null;

  const activeNode = sections.find((node) => node.section === activeSection) || null;

  return (
    <nav
      ref={navRef}
      aria-label="Categorías"
      onMouseLeave={() => setActiveSection(null)}
      className="relative border-b border-line bg-surface"
    >
      <div className="relative">
        {/* Las secciones vienen en el orden de src/shelves.py, que es
            deliberado. `justify-center-safe` centra cuando entran y, cuando no,
            alinea al principio: con `justify-center` las primeras quedarían
            cortadas fuera del alcance del scroll. */}
        <ul
          ref={listRef}
          onScroll={updateScroll}
          className="flex justify-center-safe gap-1.5 overflow-x-auto px-4 py-2 [scrollbar-width:none]"
        >
          {sections.map((node) => {
            const Icon = getSectionIcon(node.section);
            const isActive = node.section === activeSection;
            return (
              <li key={node.section} className="shrink-0">
                <button
                  type="button"
                  aria-expanded={isActive}
                  onPointerEnter={(event) => {
                    if (event.pointerType === "mouse") setActiveSection(node.section);
                  }}
                  onClick={() => setActiveSection(isActive ? null : node.section)}
                  className={`flex items-center gap-1.5 whitespace-nowrap rounded-md border px-2.5 py-2 text-sm font-medium transition-colors ${
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

        {/* Sólo con mouse (`pointer-fine`): en un touchscreen la fila se
            desliza con el dedo y las flechas taparían botones. */}
        {canScroll.left && (
          <div className="pointer-events-none absolute inset-y-0 left-0 hidden items-center bg-linear-to-r from-surface from-60% to-transparent pl-2 pr-8 pointer-fine:flex">
            <button
              type="button"
              onClick={() => scrollList(-1)}
              aria-label="Ver secciones anteriores"
              className="pointer-events-auto rounded-md border border-line bg-surface p-2 text-ink hover:bg-surface-muted"
            >
              <ChevronLeft size={16} aria-hidden="true" />
            </button>
          </div>
        )}
        {canScroll.right && (
          <div className="pointer-events-none absolute inset-y-0 right-0 hidden items-center bg-linear-to-l from-surface from-60% to-transparent pl-8 pr-2 pointer-fine:flex">
            <button
              type="button"
              onClick={() => scrollList(1)}
              aria-label="Ver más secciones"
              className="pointer-events-auto rounded-md border border-line bg-surface p-2 text-ink hover:bg-surface-muted"
            >
              <ChevronRight size={16} aria-hidden="true" />
            </button>
          </div>
        )}
      </div>

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
