import { useState } from "react";
import { Route, Routes } from "react-router-dom";
import { Header } from "./components/layout/Header";
import { CartDrawer } from "./components/cart/CartDrawer";
import { LocationModal } from "./components/onboarding/LocationModal";
import { useProfile } from "./context/ProfileContext";
import { HomePage } from "./pages/HomePage";
import { SearchResultsPage } from "./pages/SearchResultsPage";
import { CartPage } from "./pages/CartPage";

function App() {
  const [isCartOpen, setCartOpen] = useState(false);
  const [isLocationOpen, setLocationOpen] = useState(false);
  const { location } = useProfile();

  // Sin dirección el modal es el onboarding y no se puede abandonar: se monta
  // sin onClose. Con dirección ya elegida, el mismo modal se abre desde el
  // Header para cambiarla y ahí sí es descartable. Un único dueño del estado,
  // para que siga habiendo un solo lugar que sepa geocodificar.
  const isOnboarding = !location;

  return (
    <div className="flex min-h-svh flex-col bg-surface-muted">
      {(isOnboarding || isLocationOpen) && (
        <LocationModal onClose={isOnboarding ? undefined : () => setLocationOpen(false)} />
      )}
      <Header onOpenCart={() => setCartOpen(true)} onOpenLocation={() => setLocationOpen(true)} />

      <main className="flex-1">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/buscar" element={<SearchResultsPage />} />
          <Route path="/categoria/:bucket" element={<SearchResultsPage />} />
          <Route path="/carrito" element={<CartPage />} />
        </Routes>
      </main>

      <CartDrawer open={isCartOpen} onClose={() => setCartOpen(false)} />
    </div>
  );
}

export default App;
