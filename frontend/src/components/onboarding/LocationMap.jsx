import { useEffect } from "react";
import { Icon } from "leaflet";
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";

import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";

// Leaflet arma las URLs de sus íconos por concatenación a partir de dónde está
// su CSS, y bajo el bundling de Vite eso apunta a archivos que no existen: el
// marcador sale roto. Por eso se declara explícitamente con los assets
// importados, que Vite sí resuelve con su hash final.
const PIN_ICON = new Icon({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  shadowSize: [41, 41],
});

const CABA_CENTER = { lat: -34.6037, lng: -58.3816 };
const CITY_ZOOM = 12;
const ADDRESS_ZOOM = 16;

function ClickHandler({ onPick }) {
  useMapEvents({
    click: (event) => onPick({ lat: event.latlng.lat, lng: event.latlng.lng }),
  });
  return null;
}

// Recentra cuando el punto cambia desde afuera (al elegir un candidato del
// buscador). MapContainer solo usa `center` en el montaje inicial, así que sin
// esto el mapa se quedaría mirando el punto anterior.
function RecenterOnChange({ position }) {
  const map = useMap();
  useEffect(() => {
    if (position) map.setView([position.lat, position.lng], ADDRESS_ZOOM);
  }, [map, position]);
  return null;
}

/**
 * Mapa de selección de punto de entrega: OpenStreetMap vía react-leaflet, sin
 * API key ni costo. Es puramente presentacional — quién valida la cobertura de
 * ese punto es el modal que lo contiene.
 */
export function LocationMap({ position, onPick }) {
  const center = position || CABA_CENTER;

  return (
    <MapContainer
      center={[center.lat, center.lng]}
      zoom={position ? ADDRESS_ZOOM : CITY_ZOOM}
      scrollWheelZoom={false}
      className="h-56 w-full rounded-md"
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      />
      <ClickHandler onPick={onPick} />
      <RecenterOnChange position={position} />
      {position && (
        <Marker
          position={[position.lat, position.lng]}
          icon={PIN_ICON}
          draggable
          eventHandlers={{
            dragend: (event) => {
              const { lat, lng } = event.target.getLatLng();
              onPick({ lat, lng });
            },
          }}
        />
      )}
    </MapContainer>
  );
}
