// Geocodificación de direcciones vía Nominatim (OpenStreetMap).
//
// No pasa por api/client.js a propósito: ese apunta a VITE_API_URL (nuestro
// backend) y esto es un host externo.
//
// La política de uso de Nominatim admite 1 request por segundo, así que la
// búsqueda se dispara con un submit explícito y NO con cada tecla. Un
// autocomplete la violaría de entrada y puede terminar en un bloqueo por IP.

import { resolveZoneFromAddress } from "../utils/deliveryCosts";

const NOMINATIM_URL = "https://nominatim.openstreetmap.org/search";
const NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse";

/**
 * Convierte una dirección escrita a mano en candidatos con lat/lng.
 *
 * Devuelve varios resultados en vez de uno solo para que el usuario elija: en
 * Argentina hay calles con el mismo nombre en decenas de partidos, y quedarse
 * con el primer match a ciegas ata la cuenta a la sucursal equivocada.
 *
 * Cada candidato trae su `zone` derivada del `address` estructurado, que ya se
 * venía pidiendo (addressdetails=1) y se descartaba. Es lo que reemplazó al
 * dropdown manual de zona de envío.
 */
export async function geocodeAddress(query, { limit = 5 } = {}) {
  const trimmed = (query || "").trim();
  if (!trimmed) return [];

  const params = new URLSearchParams({
    q: trimmed,
    format: "json",
    countrycodes: "ar",
    addressdetails: "1",
    limit: String(limit),
  });

  const response = await fetch(`${NOMINATIM_URL}?${params}`, {
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error(`Nominatim respondió ${response.status}`);
  }

  const results = await response.json();
  if (!Array.isArray(results)) return [];

  return results.map((item) => ({
    displayName: item.display_name,
    lat: Number(item.lat),
    lng: Number(item.lon),
    zone: resolveZoneFromAddress(item.address),
  }));
}

/**
 * Datos legibles de un punto del mapa (lat/lng → `{displayName, zone}`).
 *
 * Se llama solo al soltar el pin o al clickear, nunca mientras se arrastra: la
 * misma regla de 1 req/s de arriba, que un dragend continuo violaría de sobra.
 *
 * Devuelve null si falla en vez de lanzar: la dirección escrita es cosmética
 * —lo que decide cobertura son las coordenadas—, así que un Nominatim caído no
 * puede impedir que el usuario confirme el punto que eligió. En ese caso el
 * punto queda sin `zone` y el costo de envío cae al default por zona.
 */
export async function reverseGeocode({ lat, lng }) {
  try {
    const params = new URLSearchParams({
      lat: String(lat),
      lon: String(lng),
      format: "json",
      zoom: "18",
      addressdetails: "1",
    });

    const response = await fetch(`${NOMINATIM_REVERSE_URL}?${params}`, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return null;

    const result = await response.json();
    if (!result?.display_name) return null;

    return {
      displayName: result.display_name,
      zone: resolveZoneFromAddress(result.address),
    };
  } catch {
    return null;
  }
}
