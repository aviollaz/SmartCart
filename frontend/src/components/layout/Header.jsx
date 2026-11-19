import { Link } from "react-router-dom";
import { BadgePercent, CircleHelp, MapPin, ShoppingCart, Store } from "lucide-react";
import { SearchBar } from "./SearchBar";
import { SectionBar } from "../megamenu/SectionBar";
import { useCart } from "../../context/CartContext";
import { useProfile } from "../../context/ProfileContext";
import { useCartProductsContext } from "../../context/CartProductsContext";
import { formatPrice, formatShortAddress } from "../../utils/formatters";
import { STORES } from "../../utils/constants";

export function Header({ onOpenCart, onOpenLocation, onOpenMemberships, onOpenStores }) {
  const { itemCount } = useCart();
  const { subtotalEstimado } = useCartProductsContext();
  const { location, memberships, excludedStores } = useProfile();

  // Reemplaza al viejo "Envío a {zona}", que linkeaba al carrito: la zona es un
  // dato secundario que se sigue editando en el perfil, mientras que la
  // dirección decide qué tiendas entregan y hay que poder cambiarla desde
  // cualquier página.
  const shortAddress = formatShortAddress(location);
  // Las membresías cambian los precios de toda la grilla, así que corregirlas
  // tiene que estar a un clic desde cualquier página, igual que la dirección.
  const membershipCount = memberships?.length ?? 0;
  // Lo mismo con los súper habilitados: sacan ofertas de toda la grilla.
  const enabledStores = STORES.length - excludedStores.length;

  return (
    <header className="sticky top-0 z-30">
      <div className="bg-brand-violet-900 text-white">
        {/* Una sola fila también en el celular: ahí los textos se acortan (sin
            "Envío a", "Clubes", "Súper 5/6", Ayuda sólo con el ícono) y la
            dirección se recorta. Una fila que scrollea de costado no la
            descubre nadie. */}
        <div className="mx-auto flex max-w-7xl items-center justify-between whitespace-nowrap px-4 py-1.5 text-xs">
          <button
            type="button"
            onClick={onOpenLocation}
            title={shortAddress ? location.displayName : "Ingresá tu dirección de entrega"}
            className="flex min-w-0 items-center gap-1.5 hover:underline"
          >
            <MapPin size={14} className="shrink-0" aria-hidden="true" />
            <span className="truncate">
              {shortAddress ? (
                <>
                  <span className="hidden sm:inline">Envío a </span>
                  {shortAddress}
                </>
              ) : (
                "Ingresar ubicación"
              )}
            </span>
          </button>
          <button
            type="button"
            onClick={onOpenMemberships}
            title="Clubes de supermercado: cambian los precios que ves"
            className="ml-3 flex items-center gap-1.5 hover:underline sm:ml-4"
          >
            <BadgePercent size={14} aria-hidden="true" />
            <span className="sm:hidden">{membershipCount > 0 ? `Clubes (${membershipCount})` : "Clubes"}</span>
            <span className="hidden sm:inline">
              {membershipCount > 0 ? `Mis clubes (${membershipCount})` : "Sin clubes"}
            </span>
          </button>
          <button
            type="button"
            onClick={onOpenStores}
            title="Supermercados que se usan para comparar"
            className="ml-3 mr-auto flex items-center gap-1.5 hover:underline sm:ml-4"
          >
            <Store size={14} aria-hidden="true" />
            <span className="sm:hidden">
              {enabledStores === STORES.length ? "Súper" : `Súper ${enabledStores}/${STORES.length}`}
            </span>
            <span className="hidden sm:inline">
              {enabledStores === STORES.length ? "Todos los súper" : `Súper (${enabledStores} de ${STORES.length})`}
            </span>
          </button>
          <Link to="/ayuda" aria-label="Ayuda" className="ml-3 flex items-center gap-1.5 hover:underline sm:ml-4">
            <CircleHelp size={14} aria-hidden="true" />
            <span className="hidden sm:inline">Ayuda</span>
          </Link>
        </div>
      </div>

      {/* En pantalla chica el buscador baja a su propia fila (`order-last` +
          `w-full` sobre un contenedor que envuelve) y las dos acciones dejan
          sólo el ícono. Antes era un flex de cuatro elementos sin un solo
          breakpoint: a 375 px el buscador quedaba de unos pocos caracteres, y
          casi todo el mundo va a abrir esto del celular. */}
      <div className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 md:flex-nowrap md:gap-4">
          <Link
            to="/"
            className="flex shrink-0 items-center gap-1.5 font-display text-lg font-bold text-brand-violet-700 sm:text-xl"
          >
            <ShoppingCart size={24} aria-hidden="true" />
            SmartCart
          </Link>

          <SearchBar className="order-last w-full md:order-none md:mx-auto md:w-auto" />

          <button
            type="button"
            onClick={onOpenCart}
            aria-label="Carrito"
            className="relative ml-auto flex shrink-0 items-center gap-2 rounded-md bg-brand-violet-700 px-3 py-2 text-sm font-semibold text-white hover:bg-brand-violet-900 sm:px-4 md:ml-0"
          >
            <ShoppingCart size={18} aria-hidden="true" />
            {/* El mismo subtotal estimado del carrito (CartProductsContext),
                visible mientras se eligen productos sin abrir el drawer. */}
            <span className="hidden sm:inline">
              {subtotalEstimado !== null ? `~${formatPrice(subtotalEstimado)}` : "Carrito"}
            </span>
            {itemCount > 0 && (
              <span className="absolute -right-2 -top-2 flex h-5 min-w-5 items-center justify-center rounded-full bg-brand-accent px-1 text-xs font-semibold text-white">
                {itemCount}
              </span>
            )}
          </button>
        </div>
      </div>

      <SectionBar />
    </header>
  );
}
