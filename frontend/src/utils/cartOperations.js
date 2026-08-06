/**
 * Transformaciones puras sobre el mapa del carrito ({ [unified_id]: {name, quantity} }).
 *
 * Viven acá y no adentro de CartContext para poder probarlas sin montar React:
 * son la parte del carrito donde un error no se ve (queda un producto de más o
 * una cantidad mal) en vez de romper la pantalla.
 */

/**
 * Aplica un lote de reemplazos: cada `{ from, to, name }` mueve la cantidad de
 * `from` a `to`. Los `from` que no están en el carrito se ignoran.
 *
 * Las dos pasadas son necesarias, no estilo: en una sola, el `from` de un swap
 * posterior puede borrar el `to` que insertó uno anterior (una cadena A→B, B→C
 * se comería la B recién puesta). Primero se sacan todos los orígenes, después
 * se insertan todos los destinos.
 *
 * Si el destino ya estaba en el carrito, las cantidades se suman: dos productos
 * distintos que terminan siendo el mismo son una línea sola, no una repetida.
 *
 * Devuelve el mismo objeto recibido si no hubo nada que cambiar, para que React
 * pueda saltearse el re-render.
 */
export function applySwaps(items, swaps) {
  if (!swaps || swaps.length === 0) return items;

  const next = { ...items };
  const pending = [];

  for (const { from, to, name } of swaps) {
    const existing = next[from];
    if (!existing) continue;
    delete next[from];
    pending.push({ to, name, quantity: existing.quantity });
  }
  if (pending.length === 0) return items;

  for (const { to, name, quantity } of pending) {
    next[to] = { name, quantity: (next[to]?.quantity || 0) + quantity };
  }
  return next;
}
