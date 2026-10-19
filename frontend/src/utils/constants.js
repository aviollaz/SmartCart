// Tiendas que participan de la comparación, en un solo lugar: dibuja los
// checkboxes de disponibilidad, de acá sale el estado neutro del filtro en
// useProductFilters, y `name` alimenta storeName() para la prosa de la UI
// (formatters.js). Espeja el registro del backend (src/stores.py): mismos id y
// name, en el mismo orden, que es también la prioridad de imagen.
// tests/test_stores.py lo exige.
//
// Agregar un supermercado al frontend es agregar una entrada acá (y su columna
// en deliveryCosts.js): ningún componente nombra un store_id literal. `key` es
// la del backend: indexa `logistics` en la respuesta de /optimize y arma
// GET /logistics/{key}/coverage. `color` es sólo para el diagrama del reparto
// de la home; no son los colores de marca.
export const STORES = [
  { id: "coto_online", name: "Coto", key: "coto", label: "Disponible en Coto", color: "bg-red-500" },
  { id: "dia_online", name: "Día", key: "dia", label: "Disponible en Día", color: "bg-rose-600" },
  { id: "carrefour_online", name: "Carrefour", key: "carrefour", label: "Disponible en Carrefour", color: "bg-blue-600" },
  { id: "vea_online", name: "Vea", key: "vea", label: "Disponible en Vea", color: "bg-amber-500" },
];

// Formulario de feedback para los testers de la demo, enlazado al final de la
// FAQ (/ayuda). Vacío = el bloque de contacto no se dibuja, así la página
// funciona igual antes de tener el formulario.
export const FEEDBACK_FORM_URL =
  "https://docs.google.com/forms/d/e/1FAIpQLSeBZK0Tz0twnhLe0vVlDqAPnQEjviGu_rnx-9AYRVCv9fgCww/viewform";
