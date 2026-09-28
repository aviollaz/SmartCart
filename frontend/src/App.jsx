import { useState } from "react";
import { Route, Routes } from "react-router-dom";
import { Header } from "./components/layout/Header";
import { CartDrawer } from "./components/cart/CartDrawer";
import { LocationModal } from "./components/onboarding/LocationModal";
import { MembershipModal } from "./components/onboarding/MembershipModal";
import { useProfile } from "./context/ProfileContext";
import { HomePage } from "./pages/HomePage";
import { SearchResultsPage } from "./pages/SearchResultsPage";
import { CartPage } from "./pages/CartPage";
import { ProductPage } from "./pages/ProductPage";
import { HelpPage } from "./pages/HelpPage";

function App() {
  const [isCartOpen, setCartOpen] = useState(false);
  const [isLocationOpen, setLocationOpen] = useState(false);
  const [isMembershipsOpen, setMembershipsOpen] = useState(false);
  const { location, membershipsAsked } = useProfile();

  // Sin dirección el modal es el onboarding y no se puede abandonar: se monta
  // sin onClose. Con dirección ya elegida, el mismo modal se abre desde el
  // Header para cambiarla y ahí sí es descartable. Un único dueño del estado,
  // para que siga habiendo un solo lugar que sepa geocodificar.
  const isOnboarding = !location;
  // Segundo paso del onboarding: recién después de la dirección, así nunca hay
  // dos modales apilados.
  const askMemberships = !isOnboarding && !membershipsAsked;

  return (
    <div className="flex min-h-svh flex-col bg-surface-muted">
      {(isOnboarding || isLocationOpen) && (
        <LocationModal onClose={isOnboarding ? undefined : () => setLocationOpen(false)} />
      )}
      {askMemberships && !isLocationOpen && <MembershipModal />}
      {/* Edición desde el Header: descartable, y nunca encima de otro modal. */}
      {isMembershipsOpen && !isOnboarding && !askMemberships && !isLocationOpen && (
        <MembershipModal onClose={() => setMembershipsOpen(false)} />
      )}
      <Header
        onOpenCart={() => setCartOpen(true)}
        onOpenLocation={() => setLocationOpen(true)}
        onOpenMemberships={() => setMembershipsOpen(true)}
      />

      <main className="flex-1">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/buscar" element={<SearchResultsPage />} />
          <Route path="/categoria/:shelf" element={<SearchResultsPage />} />
          <Route path="/producto/:unifiedId" element={<ProductPage />} />
          <Route path="/ayuda" element={<HelpPage />} />
          <Route
            path="/carrito"
            element={<CartPage onOpenLocation={() => setLocationOpen(true)} />}
          />
        </Routes>
      </main>

      <CartDrawer open={isCartOpen} onClose={() => setCartOpen(false)} />
    </div>
  );
}

export default App;
