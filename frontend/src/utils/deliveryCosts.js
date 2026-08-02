// Valores idénticos al mapa hardcodeado que usaba el frontend Streamlit
// (frontend/app.py, delivery_mock) para no perder paridad funcional.
export const DELIVERY_ZONES = ["CABA", "GBA Norte", "GBA Sur", "GBA Oeste"];

// Carrefour cobra lo mismo en todas las zonas a las que llega, así que su
// número se repite: es el dato, no un placeholder pendiente de afinar.
export const DELIVERY_COSTS_BY_ZONE = {
  CABA: { coto_online: 2500.0, dia_online: 2000.0, carrefour_online: 3500.0 },
  "GBA Norte": { coto_online: 3500.0, dia_online: 3000.0, carrefour_online: 3500.0 },
  "GBA Sur": { coto_online: 4000.0, dia_online: 4000.0, carrefour_online: 3500.0 },
  "GBA Oeste": { coto_online: 3800.0, dia_online: 3500.0, carrefour_online: 3500.0 },
};

// Siempre devuelve el objeto completo, con las TRES tiendas. Es una invariante,
// no una casualidad: src/optimizer.py indexa delivery_costs[store] para cada
// tienda de min_spend_limits (un faltante es KeyError, no un default), y
// src/api.py deriva de sus claves las tiendas de los baselines.
export function getDeliveryCostsForZone(zone) {
  return DELIVERY_COSTS_BY_ZONE[zone] || DELIVERY_COSTS_BY_ZONE[DELIVERY_ZONES[0]];
}

// Partidos del AMBA agrupados por zona de envío. Es dato, no lógica: si falta
// uno, agregarlo es una línea. Las claves van normalizadas (minúsculas y sin
// acentos) porque Nominatim devuelve "Morón" pero también "Moron" según el
// campo del que se lea el partido.
const PARTIDO_ZONES = {
  // Norte
  "vicente lopez": "GBA Norte",
  "san isidro": "GBA Norte",
  "san fernando": "GBA Norte",
  tigre: "GBA Norte",
  escobar: "GBA Norte",
  pilar: "GBA Norte",
  "general san martin": "GBA Norte",
  "san martin": "GBA Norte",
  "tres de febrero": "GBA Norte",
  "san miguel": "GBA Norte",
  "jose c. paz": "GBA Norte",
  "jose c paz": "GBA Norte",
  "malvinas argentinas": "GBA Norte",

  // Oeste
  "la matanza": "GBA Oeste",
  moron: "GBA Oeste",
  merlo: "GBA Oeste",
  moreno: "GBA Oeste",
  ituzaingo: "GBA Oeste",
  hurlingham: "GBA Oeste",
  "general rodriguez": "GBA Oeste",
  "marcos paz": "GBA Oeste",

  // Sur
  avellaneda: "GBA Sur",
  lanus: "GBA Sur",
  "lomas de zamora": "GBA Sur",
  quilmes: "GBA Sur",
  berazategui: "GBA Sur",
  "florencio varela": "GBA Sur",
  "almirante brown": "GBA Sur",
  "esteban echeverria": "GBA Sur",
  ezeiza: "GBA Sur",
  "san vicente": "GBA Sur",
  "presidente peron": "GBA Sur",
  berisso: "GBA Sur",
  ensenada: "GBA Sur",
  "la plata": "GBA Sur",
};

const CABA_STATES = new Set([
  "ciudad autonoma de buenos aires",
  "caba",
  "buenos aires f.d.",
]);

const PROVINCIA_BUENOS_AIRES = "buenos aires";

function normalize(value) {
  return (value || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "") // diacríticos separados por NFD
    .trim()
    .toLowerCase();
}

/**
 * Zona de envío a partir del objeto `address` de Nominatim (addressdetails=1),
 * o null si no se puede determinar.
 *
 * Reemplaza al viejo dropdown "Zona de envío": la dirección exacta es la única
 * fuente de verdad, y el usuario ya no puede tener una dirección en San Isidro
 * declarando "CABA".
 *
 * La forma del payload está relevada contra respuestas reales, no supuesta:
 *   CABA         -> state: "Ciudad Autónoma de Buenos Aires"
 *   GBA          -> state: "Buenos Aires" + state_district: "Partido de Morón"
 *   GBA (a veces) -> state: "Buenos Aires" sin state_district, con city: "Quilmes"
 *   resto del país -> state: "Córdoba", etc.
 *
 * `null` significa "no sabemos", no error: getDeliveryCostsForZone() ya cae al
 * default para cualquier valor desconocido. Cubre tres casos reales — dirección
 * fuera del AMBA, punto marcado en el mapa cuyo reverse geocoding falló, y
 * perfiles guardados antes de que este campo existiera.
 */
export function resolveZoneFromAddress(address) {
  if (!address) return null;

  const state = normalize(address.state);
  if (CABA_STATES.has(state)) return "CABA";
  if (state !== PROVINCIA_BUENOS_AIRES) return null;

  // El partido aparece en state_district cuando viene ("Partido de San Isidro");
  // si no, el municipio queda en city/town/municipality según la zona.
  const candidates = [
    normalize(address.state_district).replace(/^partido de\s+/, ""),
    normalize(address.municipality).replace(/^municipio de\s+/, ""),
    normalize(address.city),
    normalize(address.town),
  ];

  for (const candidate of candidates) {
    if (candidate && PARTIDO_ZONES[candidate]) return PARTIDO_ZONES[candidate];
  }

  // Provincia de Buenos Aires pero fuera del AMBA (Mar del Plata, Bahía Blanca):
  // ninguna de las 4 zonas aplica de verdad.
  return null;
}
