import { apiFetch } from "./client";

/**
 * Sube la foto de un ticket y devuelve, por cada línea que el OCR pudo leer,
 * el producto del catálogo más parecido (o `matched: null` si no hubo uno
 * confiable). Ver `POST /receipt/parse` en src/api.py.
 *
 * `headers: {}` pisa el `Content-Type: application/json` que pone `apiFetch`
 * por default: con FormData el browser tiene que elegir su propio boundary de
 * multipart, así que fijar el header a mano rompería el upload.
 *
 * Esto NUNCA toca el carrito por sí solo -- devuelve candidatos para que la
 * pantalla de revisión los confirme uno por uno.
 */
export function parseReceipt(file) {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch("/receipt/parse", {
    method: "POST",
    body: formData,
    headers: {},
  });
}
