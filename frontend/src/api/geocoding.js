// Geocodificación de direcciones vía Nominatim (OpenStreetMap).
//
// No pasa por api/client.js a propósito: ese apunta a VITE_API_URL (nuestro
// backend) y esto es un host externo.
//
// La política de uso de Nominatim admite 1 request por segundo, así que la
// búsqueda se dispara con un submit explícito y NO con cada tecla. Un
// autocomplete la violaría de entrada y puede terminar en un bloqueo por IP.

const NOMINATIM_URL = "https://nominatim.openstreetmap.org/search";
const NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse";

/**
 * Convierte una dirección escrita a mano en candidatos con lat/lng.
 *
 * Devuelve varios resultados en vez de uno solo para que el usuario elija: en
 * Argentina hay calles con el mismo nombre en decenas de partidos, y quedarse
 * con el primer match a ciegas ata la cuenta a la sucursal equivocada.
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
  }));
}

/**
 * Nombre legible de un punto del mapa (lat/lng → dirección).
 *
 * Se llama solo al soltar el pin o al clickear, nunca mientras se arrastra: la
 * misma regla de 1 req/s de arriba, que un dragend continuo violaría de sobra.
 *
 * Devuelve null si falla en vez de lanzar: la dirección escrita es cosmética
 * —lo que decide cobertura y envío son las coordenadas—, así que un Nominatim
 * caído no puede impedir que el usuario confirme el punto que eligió.
 */
export async function reverseGeocode({ lat, lng }) {
  try {
    const params = new URLSearchParams({
      lat: String(lat),
      lon: String(lng),
      format: "json",
      zoom: "18",
    });

    const response = await fetch(`${NOMINATIM_REVERSE_URL}?${params}`, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return null;

    const result = await response.json();
    return result?.display_name || null;
  } catch {
    return null;
  }
}
