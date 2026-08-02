import { useEffect, useState } from "react";
import { MapPin, Search, X } from "lucide-react";
import { geocodeAddress, reverseGeocode } from "../../api/geocoding";
import { checkCotoCoverage } from "../../api/logistics";
import { useProfile } from "../../context/ProfileContext";
import { LocationMap } from "./LocationMap";

/**
 * Onboarding de dirección: bloquea la app hasta que haya coordenadas.
 *
 * La dirección deja de ser cosmética con este feature: determina si Coto puede
 * entregar y cuánto cobra, y eso cambia el resultado del optimizador.
 *
 * Tiene salida ("seguir sin dirección"): si Nominatim está caído o no encuentra
 * el domicilio, un modal sin escape dejaría la app inutilizable. Al saltear se
 * cae al comportamiento por zona de siempre.
 *
 * El buscador y el mapa son dos formas de fijar el mismo punto: elegir un
 * candidato mueve el pin, y arrastrarlo o clickear el mapa corrige lo que el
 * geocoder haya errado. Recién el botón de confirmar consulta la cobertura.
 *
 * `onClose` es lo único que distingue el onboarding de un cambio de dirección
 * desde el Header: cuando viene, el modal se puede abandonar (X, Escape o clic
 * afuera) y la dirección vigente queda intacta. Sin la prop sigue siendo
 * bloqueante, porque en el onboarding cerrar sin elegir dejaría a la app sin
 * ninguno de los dos estados válidos (dirección o "seguir sin dirección").
 */
export function LocationModal({ onClose }) {
  const { location, setLocation, skipLocation } = useProfile();

  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState([]);
  const [status, setStatus] = useState("idle"); // idle | searching | empty | error | confirming
  const [coverageWarning, setCoverageWarning] = useState(null);
  // Punto elegido pero todavía no confirmado: {displayName, lat, lng}. Arranca
  // en la dirección vigente (si hay) para que el mapa abra con el pin puesto
  // donde el usuario ya está, en vez de mandarlo de nuevo al centro de CABA.
  const [pendingPoint, setPendingPoint] = useState(() =>
    location && !location.skipped && typeof location.lat === "number"
      ? { displayName: location.displayName, lat: location.lat, lng: location.lng }
      : null
  );

  useEffect(() => {
    if (!onClose) return;
    function onKeyDown(event) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  async function handleSearch(event) {
    event.preventDefault();
    if (!query.trim()) return;

    setStatus("searching");
    setCoverageWarning(null);
    try {
      const results = await geocodeAddress(query);
      setCandidates(results);
      setStatus(results.length === 0 ? "empty" : "idle");
    } catch {
      setCandidates([]);
      setStatus("error");
    }
  }

  function selectCandidate(candidate) {
    setCoverageWarning(null);
    setPendingPoint(candidate);
  }

  // Al soltar el pin o clickear el mapa. El reverse geocoding se pide una sola
  // vez por gesto terminado (nunca durante el arrastre) por la política de 1
  // req/s de Nominatim, y su resultado es opcional: si no viene, quedan las
  // coordenadas, que son lo único que el backend realmente necesita.
  async function handleMapPick({ lat, lng }) {
    setCoverageWarning(null);
    setPendingPoint({ displayName: null, lat, lng });

    const displayName = await reverseGeocode({ lat, lng });
    if (!displayName) return;
    // Se descarta si el usuario ya movió el pin de nuevo mientras respondía.
    setPendingPoint((prev) =>
      prev && prev.lat === lat && prev.lng === lng ? { ...prev, displayName } : prev
    );
  }

  function persist(point, coverage) {
    setLocation(
      {
        displayName: point.displayName || formatCoords(point),
        lat: point.lat,
        lng: point.lng,
      },
      coverage ? { coto_online: coverage } : {}
    );
    // En el onboarding no hay nada que cerrar: el modal desaparece solo cuando
    // App.jsx ve que ya hay location.
    onClose?.();
  }

  async function handleConfirm() {
    if (!pendingPoint) return;
    setStatus("confirming");

    // Se consulta la cobertura antes de cerrar para poder avisar acá mismo, en
    // vez de que el usuario se entere recién al optimizar. Un ok:false es "no
    // pudimos preguntar", no "no hay cobertura": no bloquea la confirmación ni
    // se guarda como veredicto.
    const coverage = await checkCotoCoverage(pendingPoint);

    if (coverage.ok && coverage.covered === false) {
      setCoverageWarning({
        coverage,
        message: coverage.mensaje || "Coto no realiza entregas en esta dirección.",
      });
      setStatus("idle");
      return;
    }

    persist(pendingPoint, coverage.ok ? coverage : null);
  }

  // El veredicto negativo se guarda junto con la dirección: es lo que después
  // saca los productos de esa tienda del catálogo.
  function acceptWithoutCoto() {
    persist(pendingPoint, coverageWarning.coverage);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose ? (event) => event.target === event.currentTarget && onClose() : undefined}
    >
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-line bg-surface p-6 shadow-lg">
        <div className="mb-4 flex items-center gap-2">
          <MapPin className="text-brand-accent" size={20} />
          <h2 className="font-display text-lg font-bold text-ink">¿A dónde te llevamos el pedido?</h2>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Cerrar"
              className="ml-auto rounded-md p-1 text-ink-muted hover:bg-surface-muted hover:text-ink"
            >
              <X size={18} />
            </button>
          )}
        </div>

        <p className="mb-4 text-sm text-ink-muted">
          Necesitamos tu dirección para saber si los supermercados entregan en tu zona y cuánto
          cuesta el envío. Sin eso, el precio final es una estimación.
        </p>

        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Ej: Av. Corrientes 1234, CABA"
            className="flex-1 rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink"
            autoFocus
          />
          <button
            type="submit"
            disabled={status === "searching" || !query.trim()}
            className="flex items-center gap-2 rounded-md bg-brand-accent px-4 py-2 text-sm font-semibold text-white hover:bg-brand-accent-dark disabled:opacity-50"
          >
            <Search size={14} />
            {status === "searching" ? "Buscando..." : "Buscar"}
          </button>
        </form>

        {status === "empty" && (
          <p className="mt-3 text-sm text-state-warning">
            No encontramos esa dirección. Probá agregando la localidad o el partido, o marcá el
            punto directamente en el mapa.
          </p>
        )}

        {status === "error" && (
          <p className="mt-3 text-sm text-state-warning">
            No pudimos buscar la dirección en este momento. Marcá el punto en el mapa o seguí sin
            dirección.
          </p>
        )}

        {candidates.length > 0 && (
          <ul className="mt-4 max-h-40 divide-y divide-line overflow-y-auto rounded-md border border-line">
            {candidates.map((candidate) => {
              const selected = isSamePoint(pendingPoint, candidate);
              return (
                <li key={`${candidate.lat},${candidate.lng}`}>
                  <button
                    type="button"
                    onClick={() => selectCandidate(candidate)}
                    className={`w-full px-3 py-2 text-left text-sm hover:bg-surface-muted ${
                      selected ? "bg-brand-violet-100 font-semibold text-ink" : "text-ink"
                    }`}
                  >
                    {candidate.displayName}
                  </button>
                </li>
              );
            })}
          </ul>
        )}

        <div className="mt-4">
          <p className="mb-2 text-xs text-ink-muted">
            {pendingPoint
              ? "Arrastrá el pin o hacé clic en el mapa para ajustar el punto exacto."
              : "También podés marcar tu ubicación haciendo clic en el mapa."}
          </p>
          <LocationMap position={pendingPoint} onPick={handleMapPick} />
        </div>

        {pendingPoint && (
          <p className="mt-3 text-sm text-ink">
            <span className="font-semibold">Ubicación elegida: </span>
            {pendingPoint.displayName || formatCoords(pendingPoint)}
          </p>
        )}

        {coverageWarning && (
          <div className="mt-3 rounded-md border border-state-warning/40 bg-state-warning/10 p-3">
            <p className="text-sm font-semibold text-ink">Coto no entrega en esta dirección</p>
            <p className="mt-1 text-xs text-ink-muted">{coverageWarning.message}</p>
            <button
              type="button"
              onClick={acceptWithoutCoto}
              className="mt-2 text-sm font-semibold text-brand-accent underline"
            >
              Usar igual esta dirección (sin Coto)
            </button>
          </div>
        )}

        <button
          type="button"
          onClick={handleConfirm}
          disabled={!pendingPoint || status === "confirming"}
          className="mt-4 w-full rounded-md bg-brand-violet-700 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-violet-900 disabled:opacity-50"
        >
          {status === "confirming" ? "Verificando cobertura..." : "Confirmar esta ubicación"}
        </button>

        <button
          type="button"
          onClick={() => {
            skipLocation();
            onClose?.();
          }}
          className="mt-3 w-full text-center text-xs text-ink-muted underline hover:text-ink"
        >
          Seguir sin dirección (usamos costos de envío estimados por zona)
        </button>
      </div>
    </div>
  );
}

function formatCoords({ lat, lng }) {
  return `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
}

function isSamePoint(a, b) {
  return Boolean(a && b && a.lat === b.lat && a.lng === b.lng);
}
