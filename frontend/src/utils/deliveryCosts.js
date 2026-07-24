// Valores idénticos al mapa hardcodeado que usaba el frontend Streamlit
// (frontend/app.py, delivery_mock) para no perder paridad funcional.
export const DELIVERY_ZONES = ["CABA", "GBA Norte", "GBA Sur", "GBA Oeste"];

export const DELIVERY_COSTS_BY_ZONE = {
  CABA: { coto_online: 2500.0, dia_online: 2000.0 },
  "GBA Norte": { coto_online: 3500.0, dia_online: 3000.0 },
  "GBA Sur": { coto_online: 4000.0, dia_online: 4000.0 },
  "GBA Oeste": { coto_online: 3800.0, dia_online: 3500.0 },
};

export function getDeliveryCostsForZone(zone) {
  return DELIVERY_COSTS_BY_ZONE[zone] || DELIVERY_COSTS_BY_ZONE[DELIVERY_ZONES[0]];
}
