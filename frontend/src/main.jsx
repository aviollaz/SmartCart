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
import { HistoryProvider } from './context/HistoryContext.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <CartProvider>
        <ProfileProvider>
          {/* El más interno: no necesita nada de los otros dos, pero desde acá
              puede leerlos si alguna vez hace falta, y nadie arriba lo necesita. */}
          <HistoryProvider>
            <App />
          </HistoryProvider>
        </ProfileProvider>
      </CartProvider>
    </BrowserRouter>
  </StrictMode>,
)
