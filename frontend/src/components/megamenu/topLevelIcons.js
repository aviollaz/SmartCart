import {
  Baby,
  Beef,
  Beer,
  Bike,
  Cookie,
  Home,
  IceCreamCone,
  Layers,
  MonitorSmartphone,
  PawPrint,
  Shirt,
  ShoppingBasket,
  Snowflake,
  Sparkles,
  Sprout,
  Tag,
  Tent,
  Wine,
} from "lucide-react";

// Mapeo best-effort nombre-de-categoría -> ícono (matching por substring,
// case-insensitive). Un ícono genérico cubre cualquier top-level no mapeado
// explícitamente, ya que el árbol real tiene ~15-20 categorías y no todas
// necesitan un ícono a medida para ser usables.
const ICON_RULES = [
  [/almac[eé]n/i, ShoppingBasket],
  [/bebida/i, Wine],
  [/beb[eé]s|ni[ñn]os/i, Baby],
  [/congelado/i, Snowflake],
  [/frescos/i, Beef],
  [/hogar/i, Home],
  [/limpieza/i, Sparkles],
  [/perfumer[ií]a/i, Sparkles],
  [/mascota/i, PawPrint],
  [/tecnolog[ií]a/i, MonitorSmartphone],
  [/textil|indumentaria/i, Shirt],
  [/aire libre/i, Tent],
  [/colchon/i, Layers],
  [/desayuno/i, Cookie],
  [/cervez|alcohol/i, Beer],
  [/jardin/i, Sprout],
  [/rodado|bici/i, Bike],
  [/postre|helado/i, IceCreamCone],
];

export function getTopLevelIcon(label) {
  const match = ICON_RULES.find(([pattern]) => pattern.test(label));
  return match ? match[1] : Tag;
}
