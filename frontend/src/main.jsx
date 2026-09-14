import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
// Antes de index.css para que los estilos propios puedan pisar a los de Leaflet
// y no al revés.
import 'leaflet/dist/leaflet.css'
import './index.css'
import App from './App.jsx'
import { CartProvider } from './context/CartContext.jsx'
import { ProfileProvider } from './context/ProfileContext.jsx'
import { CartProductsProvider } from './context/CartProductsContext.jsx'
import { HistoryProvider } from './context/HistoryContext.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <CartProvider>
        <ProfileProvider>
          {/* Necesita CartContext y ProfileContext (recorta por cobertura), así
              que va adentro de los dos. HistoryProvider no depende de esto ni
              al revés — el orden entre ambos no importa. */}
          <CartProductsProvider>
            <HistoryProvider>
              <App />
            </HistoryProvider>
          </CartProductsProvider>
        </ProfileProvider>
      </CartProvider>
    </BrowserRouter>
  </StrictMode>,
)
