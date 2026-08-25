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

/**
 * Suma un carrito entero al actual, para el "Repetir" del historial.
 *
 * Es un merge y no un reemplazo a propósito. `restoreItems` existe y sería más
 * corto, pero borra lo que el usuario ya tenía — y el mismo botón vive en dos
 * lados: en /carrito sólo aparece con el carrito vacío, pero en la home el
 * carrito puede estar lleno. Un botón que en una pantalla significa "agregar" y
 * en otra "descartar todo" es peor que cualquiera de las dos cosas, y no hay
 * nada en el botón que avise. El merge además se deshace con los steppers que ya
 * están; el reemplazo necesitaría una UndoBar propia.
 *
 * Va en una sola escritura y no en N llamadas a addItem por el mismo motivo que
 * applySwaps: N llamadas son N renders y N escrituras a localStorage.
 *
 * Cuando el producto ya estaba en el carrito se conserva el nombre ACTUAL: ese
 * salió de un ProductResponse vivo, mientras que el del historial puede tener
 * meses.
 *
 * Devuelve el mismo objeto recibido si no había nada que agregar, para que React
 * pueda saltearse el re-render.
 */
export function mergeItems(items, incoming) {
  const uids = Object.keys(incoming || {});
  if (uids.length === 0) return items;

  const next = { ...items };
  for (const unifiedId of uids) {
    const entrante = incoming[unifiedId];
    const cantidad = entrante?.quantity || 0;
    if (cantidad <= 0) continue;

    const existente = next[unifiedId];
    next[unifiedId] = {
      name: existente?.name || entrante?.name || unifiedId,
      quantity: (existente?.quantity || 0) + cantidad,
    };
  }
  return next;
}
