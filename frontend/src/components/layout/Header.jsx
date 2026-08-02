import { useState } from "react";
import { Link } from "react-router-dom";
import { Menu, MapPin, ShoppingCart } from "lucide-react";
import { SearchBar } from "./SearchBar";
import { MegaMenu } from "../megamenu/MegaMenu";
import { useCart } from "../../context/CartContext";
import { useProfile } from "../../context/ProfileContext";
import { formatShortAddress } from "../../utils/formatters";

export function Header({ onOpenCart, onOpenLocation }) {
  const [isMegaMenuOpen, setMegaMenuOpen] = useState(false);
  const { itemCount } = useCart();
  const { location } = useProfile();

  // Reemplaza al viejo "Envío a {zona}", que linkeaba al carrito: la zona es un
  // dato secundario que se sigue editando en el perfil, mientras que la
  // dirección decide qué tiendas entregan y hay que poder cambiarla desde
  // cualquier página.
  const shortAddress = formatShortAddress(location);

  return (
    <header className="sticky top-0 z-30">
      <div className="bg-brand-violet-900 text-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-1.5 text-xs">
          <button
            type="button"
            onClick={onOpenLocation}
            title={shortAddress ? location.displayName : "Ingresá tu dirección de entrega"}
            className="flex items-center gap-1.5 hover:underline"
          >
            <MapPin size={14} aria-hidden="true" />
            {shortAddress ? `Envío a ${shortAddress}` : "Ingresar ubicación"}
          </button>
        </div>
      </div>

      <div className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3">
          <Link
            to="/"
            className="flex shrink-0 items-center gap-1.5 font-display text-xl font-bold text-brand-violet-700"
          >
            <ShoppingCart size={24} aria-hidden="true" />
            SmartCart
          </Link>

          <button
            type="button"
            onClick={() => setMegaMenuOpen(true)}
            className="flex shrink-0 items-center gap-1.5 rounded-md border border-line px-3 py-2 text-sm font-medium text-ink hover:bg-surface-muted"
          >
            <Menu size={18} aria-hidden="true" />
            Categorías
          </button>

          <SearchBar className="mx-auto" />

          <button
            type="button"
            onClick={onOpenCart}
            className="relative flex shrink-0 items-center gap-2 rounded-full border border-brand-violet-700 px-4 py-2 text-sm font-medium text-brand-violet-700 hover:bg-brand-violet-100"
          >
            <ShoppingCart size={18} aria-hidden="true" />
            Carrito
            {itemCount > 0 && (
              <span className="absolute -right-2 -top-2 flex h-5 min-w-5 items-center justify-center rounded-full bg-brand-accent px-1 text-xs font-semibold text-white">
                {itemCount}
              </span>
            )}
          </button>
        </div>
      </div>

      <MegaMenu open={isMegaMenuOpen} onClose={() => setMegaMenuOpen(false)} />
    </header>
  );
}
