import { useState } from "react";
import { Route, Routes } from "react-router-dom";
import { Header } from "./components/layout/Header";
import { CartDrawer } from "./components/cart/CartDrawer";
import { HomePage } from "./pages/HomePage";
import { SearchResultsPage } from "./pages/SearchResultsPage";
import { CartPage } from "./pages/CartPage";

function App() {
  const [isCartOpen, setCartOpen] = useState(false);

  return (
    <div className="flex min-h-svh flex-col bg-surface-muted">
      <Header onOpenCart={() => setCartOpen(true)} />

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
