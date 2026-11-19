import { useEffect, useRef } from "react";
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
// esto el mapa se quedaría mirando el punto anterior. Un punto marcado en el
// propio mapa no recentra: el zoom que el usuario eligió con la rueda saltaría
// de golpe a cada click.
function RecenterOnChange({ position, pickedRef }) {
  const map = useMap();
  useEffect(() => {
    if (!position) return;
    const picked = pickedRef.current;
    if (picked && picked.lat === position.lat && picked.lng === position.lng) return;
    map.setView([position.lat, position.lng], ADDRESS_ZOOM);
  }, [map, position, pickedRef]);
  return null;
}

/**
 * Mapa de selección de punto de entrega: OpenStreetMap vía react-leaflet, sin
 * API key ni costo. Es puramente presentacional — quién valida la cobertura de
 * ese punto es el modal que lo contiene.
 */
export function LocationMap({ position, onPick }) {
  const center = position || CABA_CENTER;
  // El último punto marcado en el mapa, para que RecenterOnChange lo ignore.
  const pickedRef = useRef(null);
  function pick(point) {
    pickedRef.current = point;
    onPick(point);
  }

  return (
    <MapContainer
      center={[center.lat, center.lng]}
      zoom={position ? ADDRESS_ZOOM : CITY_ZOOM}
      scrollWheelZoom
      className="h-40 w-full rounded-md sm:h-56"
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      />
      <ClickHandler onPick={pick} />
      <RecenterOnChange position={position} pickedRef={pickedRef} />
      {position && (
        <Marker
          position={[position.lat, position.lng]}
          icon={PIN_ICON}
          draggable
          eventHandlers={{
            dragend: (event) => {
              const { lat, lng } = event.target.getLatLng();
              pick({ lat, lng });
            },
          }}
        />
      )}
    </MapContainer>
  );
}
