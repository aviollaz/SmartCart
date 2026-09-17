import { useRef, useState } from "react";
import { Camera, Check, Loader2, Plus, Search, Trash2, X } from "lucide-react";
import { parseReceipt } from "../../api/receipt";
import { searchProducts } from "../../api/products";
import { useCart } from "../../context/CartContext";
import { formatPrice, resolveDisplayImage, resolveDisplayPrice } from "../../utils/formatters";
import { QuantityStepper } from "../plp/QuantityStepper";

/**
 * Sube la foto de un ticket, la matchea contra el catálogo (OCR + búsqueda
 * semántica de `/receipt/parse`, ver src/receipt_parser.py) y deja
 * revisar/corregir cada línea ANTES de tocar el carrito.
 *
 * El OCR sobre una impresora térmica argentina se equivoca seguido, así que
 * nada se agrega solo: cada línea arranca incluida sólo si trajo un match, y
 * el usuario puede sacarla, cambiar el match (buscando a mano) o ajustar la
 * cantidad antes de confirmar. Recién "Agregar al carrito" mezcla lo elegido
 * con `mergeItems` — mismo patrón que "Repetir" del historial y el carrito de
 * ejemplo: nunca reemplaza lo que ya había.
 */
export function ReceiptScanModal({ onClose }) {
  const { mergeItems } = useCart();
  const fileInputRef = useRef(null);
  const [status, setStatus] = useState("idle"); // idle | loading | review | error
  const [lines, setLines] = useState([]);
  const [errorMessage, setErrorMessage] = useState(null);
  const [addingManual, setAddingManual] = useState(false);

  async function handleFile(event) {
    const file = event.target.files?.[0];
    event.target.value = ""; // permite volver a elegir la misma foto
    if (!file) return;

    setStatus("loading");
    setErrorMessage(null);
    try {
      const results = await parseReceipt(file);
      setLines(results.map((r) => ({ ...r, included: Boolean(r.matched), quantity: 1 })));
      setStatus("review");
    } catch (err) {
      setErrorMessage(err?.detail || "No pudimos leer el ticket. Probá con otra foto.");
      setStatus("error");
    }
  }

  function updateLine(index, patch) {
    setLines((prev) => prev.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  }

  // El OCR no siempre separa bien nombre y precio (una línea garabateada puede
  // perder el producto entero, sin dejar ni una fila "no encontrado" para
  // corregir) -- esto es el escape para esos casos: agregar a mano lo que la
  // lectura automática ni siquiera intentó.
  function addManualLine(product) {
    setLines((prev) => [
      ...prev,
      { ocr_line: null, matched: product, distance: null, included: true, quantity: 1 },
    ]);
    setAddingManual(false);
  }

  function confirm() {
    const incoming = {};
    for (const line of lines) {
      if (!line.included || !line.matched) continue;
      incoming[line.matched.unified_id] = { name: line.matched.name, quantity: line.quantity };
    }
    mergeItems(incoming);
    onClose();
  }

  const confirmedCount = lines.filter((l) => l.included && l.matched).length;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(event) => event.target === event.currentTarget && onClose()}
    >
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-line bg-surface p-6 shadow-lg">
        <div className="mb-4 flex items-center gap-2">
          <Camera className="text-brand-accent" size={20} aria-hidden="true" />
          <h2 className="font-display text-lg font-bold text-ink">Escanear un ticket</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="ml-auto rounded-md p-1 text-ink-muted hover:bg-surface-muted hover:text-ink"
          >
            <X size={18} />
          </button>
        </div>

        {status === "idle" && (
          <>
            <p className="mb-4 text-sm text-ink-muted">
              Sacale una foto a tu ticket de compra y armamos un carrito con los productos que
              reconozcamos. Vas a poder revisar y corregir cada línea antes de agregarla.
            </p>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="w-full rounded-md bg-brand-accent px-4 py-3 text-sm font-semibold text-white hover:bg-brand-accent-dark"
            >
              Elegir foto
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              onChange={handleFile}
              className="hidden"
            />
          </>
        )}

        {status === "loading" && (
          <div className="flex flex-col items-center gap-3 py-10 text-ink-muted">
            <Loader2 className="animate-spin" size={28} aria-hidden="true" />
            <p className="text-sm">Leyendo el ticket...</p>
          </div>
        )}

        {status === "error" && (
          <>
            <p className="mb-4 text-sm text-state-warning">{errorMessage}</p>
            <button
              type="button"
              onClick={() => setStatus("idle")}
              className="w-full rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-surface-muted"
            >
              Intentar de nuevo
            </button>
          </>
        )}

        {status === "review" && (
          <>
            {lines.length === 0 ? (
              <p className="text-sm text-ink-muted">No pudimos leer ninguna línea de este ticket.</p>
            ) : (
              <ul className="space-y-3">
                {lines.map((line, index) => (
                  <ReceiptLineRow key={index} line={line} onChange={(patch) => updateLine(index, patch)} />
                ))}
              </ul>
            )}

            {/* El OCR se equivoca seguido sobre tickets reales (líneas que
                pierden el nombre y el precio a la vez) -- esto cubre lo que la
                lectura automática no llegó ni a proponer como candidato. */}
            <div className="mt-3 border-t border-line pt-3">
              {addingManual ? (
                <InlineProductSearch initialQuery="" onPick={addManualLine} onCancel={() => setAddingManual(false)} />
              ) : (
                <button
                  type="button"
                  onClick={() => setAddingManual(true)}
                  className="flex items-center gap-1 text-sm font-semibold text-brand-accent underline"
                >
                  <Plus size={14} aria-hidden="true" />
                  Agregar un producto que no reconocimos
                </button>
              )}
            </div>

            <button
              type="button"
              onClick={confirm}
              disabled={confirmedCount === 0}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-md bg-brand-violet-700 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-violet-900 disabled:opacity-50"
            >
              <Check size={16} aria-hidden="true" />
              {confirmedCount > 0
                ? `Agregar ${confirmedCount} producto${confirmedCount === 1 ? "" : "s"} al carrito`
                : "Elegí al menos un producto"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function ReceiptLineRow({ line, onChange }) {
  const [searching, setSearching] = useState(false);

  if (!line.matched) {
    return (
      <li className="rounded-md border border-line p-3">
        <p className="text-xs text-ink-muted">Leímos: "{line.ocr_line}"</p>
        <p className="mt-1 text-sm text-ink-muted">No encontramos un producto parecido.</p>
        {searching ? (
          <InlineProductSearch
            initialQuery={line.ocr_line}
            onPick={(product) => {
              onChange({ matched: product, included: true });
              setSearching(false);
            }}
            onCancel={() => setSearching(false)}
          />
        ) : (
          <button
            type="button"
            onClick={() => setSearching(true)}
            className="mt-2 flex items-center gap-1 text-sm font-semibold text-brand-accent underline"
          >
            <Search size={14} aria-hidden="true" />
            Buscar a mano
          </button>
        )}
      </li>
    );
  }

  const product = line.matched;
  const price = resolveDisplayPrice(product);
  const image = resolveDisplayImage(product);

  return (
    <li className={`rounded-md border border-line p-3 ${line.included ? "" : "opacity-50"}`}>
      <div className="flex items-start gap-3">
        {image && (
          <img src={image} alt="" className="h-12 w-12 shrink-0 rounded object-contain" />
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-ink">{product.name}</p>
          <p className="text-xs text-ink-muted">
            {line.ocr_line ? `Leímos: "${line.ocr_line}"` : "Agregado a mano"}
            {typeof price === "number" && ` · ${formatPrice(price)}`}
          </p>
        </div>
        <button
          type="button"
          onClick={() => onChange({ included: !line.included })}
          aria-label={line.included ? "Sacar de la lista" : "Volver a incluir"}
          className="shrink-0 rounded-md p-1.5 text-ink-muted hover:bg-surface-muted hover:text-ink"
        >
          <Trash2 size={16} />
        </button>
      </div>

      {line.included && (
        <div className="mt-2 flex items-center justify-between">
          {searching ? (
            <InlineProductSearch
              initialQuery=""
              onPick={(picked) => {
                onChange({ matched: picked });
                setSearching(false);
              }}
              onCancel={() => setSearching(false)}
            />
          ) : (
            <button
              type="button"
              onClick={() => setSearching(true)}
              className="text-xs font-semibold text-brand-accent underline"
            >
              Cambiar producto
            </button>
          )}
          <QuantityStepper
            size="sm"
            quantity={line.quantity}
            onIncrement={() => onChange({ quantity: line.quantity + 1 })}
            onDecrement={() => onChange({ quantity: Math.max(1, line.quantity - 1) })}
          />
        </div>
      )}
    </li>
  );
}

/** Buscador inline mínimo para corregir un match, sobre el mismo /search de siempre. */
function InlineProductSearch({ initialQuery, onPick, onCancel }) {
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      setResults(await searchProducts(query, 5));
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mt-2 w-full">
      <form onSubmit={handleSubmit} className="flex gap-1">
        <input
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Buscar producto..."
          autoFocus
          className="min-w-0 flex-1 rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink"
        />
        <button
          type="submit"
          disabled={loading}
          className="shrink-0 rounded-md bg-brand-accent px-2 py-1 text-xs font-semibold text-white disabled:opacity-50"
        >
          Buscar
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="shrink-0 rounded-md border border-line px-2 py-1 text-xs text-ink-muted"
        >
          Cancelar
        </button>
      </form>

      {results.length > 0 && (
        <ul className="mt-2 divide-y divide-line rounded-md border border-line">
          {results.map((product) => (
            <li key={product.unified_id}>
              <button
                type="button"
                onClick={() => onPick(product)}
                className="w-full px-2 py-1.5 text-left text-xs text-ink hover:bg-surface-muted"
              >
                {product.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
