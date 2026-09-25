// Tiendas que participan de la comparación, en un solo lugar: dibuja los
// checkboxes de disponibilidad, de acá sale el estado neutro del filtro en
// useProductFilters, y `name` alimenta storeName() para la prosa de la UI
// (formatters.js). Los store_id espejan las claves de
// src/optimizer.py DEFAULT_MIN_SPEND_LIMITS.
//
// Agregar un supermercado al frontend es agregar una entrada acá: ningún
// componente nombra un store_id literal.
export const STORES = [
  { id: "coto_online", name: "Coto", label: "Disponible en Coto" },
  { id: "dia_online", name: "Día", label: "Disponible en Día" },
  { id: "carrefour_online", name: "Carrefour", label: "Disponible en Carrefour" },
];

// Formulario de feedback para los testers de la demo, enlazado al final de la
// FAQ (/ayuda). Vacío = el bloque de contacto no se dibuja, así la página
// funciona igual antes de tener el formulario.
export const FEEDBACK_FORM_URL =
  "https://docs.google.com/forms/d/e/1FAIpQLSeBZK0Tz0twnhLe0vVlDqAPnQEjviGu_rnx-9AYRVCv9fgCww/viewform";
