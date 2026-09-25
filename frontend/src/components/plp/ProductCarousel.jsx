import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { ProductCard } from "./ProductCard";

/**
 * Una fila de productos con scroll horizontal y flechas a los costados.
 *
 * Existe para listas largas que no deberían empujar el resto de la página
 * hacia abajo (las ofertas de la home): 50 productos en grilla son 13 filas,
 * en carrusel son una. Las flechas avanzan casi una pantalla de cards; el
 * scroll nativo (rueda, trackpad, swipe en el celular) sigue funcionando.
 *
 * Las flechas van en el encabezado, a la derecha del título, y no sobre la
 * fila: montadas encima de las cards tapaban el precio de la primera y la
 * última. Cada una se deshabilita cuando no hay nada para ese lado.
 *
 * `title` es el contenido del encabezado; `label` nombra la lista para
 * lectores de pantalla.
 */
export function ProductCarousel({ products, title, label }) {
  const trackRef = useRef(null);
  const [edges, setEdges] = useState({ atStart: true, atEnd: true });

  const updateEdges = useCallback(() => {
    const track = trackRef.current;
    if (!track) return;
    // 1 px de tolerancia: con zoom del navegador scrollLeft puede quedar en
    // un decimal y la flecha nunca desaparecería.
    setEdges({
      atStart: track.scrollLeft <= 1,
      atEnd: track.scrollLeft + track.clientWidth >= track.scrollWidth - 1,
    });
  }, []);

  useEffect(() => {
    updateEdges();
    window.addEventListener("resize", updateEdges);
    return () => window.removeEventListener("resize", updateEdges);
  }, [updateEdges, products]);

  function scrollByPage(direction) {
    const track = trackRef.current;
    if (!track) return;
    // 90% del ancho visible: la última card de la vista anterior queda
    // asomada y el usuario no pierde el hilo de dónde estaba.
    track.scrollBy({ left: direction * track.clientWidth * 0.9, behavior: "smooth" });
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3">
        {title}
        <div className="flex shrink-0 gap-2">
          <ArrowButton direction="left" disabled={edges.atStart} onClick={() => scrollByPage(-1)} />
          <ArrowButton direction="right" disabled={edges.atEnd} onClick={() => scrollByPage(1)} />
        </div>
      </div>
      <ul
        ref={trackRef}
        onScroll={updateEdges}
        aria-label={label}
        className="flex snap-x snap-mandatory gap-4 overflow-x-auto scroll-smooth pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {products.map((product) => (
          <li key={product.unified_id} className="flex w-44 shrink-0 snap-start sm:w-56">
            <ProductCard product={product} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function ArrowButton({ direction, disabled, onClick }) {
  const Icon = direction === "left" ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={direction === "left" ? "Ver anteriores" : "Ver más"}
      className="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-surface text-brand-violet-700 transition-colors hover:bg-brand-violet-100 disabled:cursor-default disabled:opacity-40 disabled:hover:bg-surface"
    >
      <Icon size={20} />
    </button>
  );
}
