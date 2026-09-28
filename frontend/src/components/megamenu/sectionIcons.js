import { Apple, Beef, Cookie, Milk, ShoppingBasket, Snowflake, Sparkles, SprayCan, Tag, Wine } from "lucide-react";

// Sección -> ícono. Las secciones salen de `SECTIONS` en src/shelves.py y hoy
// son nueve, así que el mapeo es exacto y no un matching por substring: la
// versión anterior tenía 18 reglas regex porque tenía que cubrir la taxonomía
// completa de dos cadenas, con top-levels que el catálogo no tenía
// ("Mascotas", "Rodados").
//
// `Tag` cubre cualquier sección nueva mientras no se le elija un ícono: agregar
// una góndola en una sección inédita no puede romper el menú.
const SECTION_ICONS = {
  "Almacén": ShoppingBasket,
  "Frescos": Milk,
  "Frutas y verduras": Apple,
  "Carnes": Beef,
  "Desayuno y merienda": Cookie,
  "Bebidas": Wine,
  "Congelados": Snowflake,
  "Limpieza": SprayCan,
  "Perfumería": Sparkles,
};

export function getSectionIcon(section) {
  return SECTION_ICONS[section] || Tag;
}
