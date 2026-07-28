import { createContext, useContext, useMemo } from "react";
import { useLocalStorage } from "../hooks/useLocalStorage";
import { DELIVERY_ZONES, getDeliveryCostsForZone } from "../utils/deliveryCosts";

const ProfileContext = createContext(null);

const STORAGE_KEY = "smartcart_profile_v1";

// Referencia estable para el caso "no sabemos nada de cobertura": `useProductFilters`
// la usa como dependencia de un useMemo, y un [] nuevo por render lo invalidaría siempre.
const NO_UNAVAILABLE_STORES = [];

const DEFAULT_PROFILE = {
  cards: [],
  memberships: [],
  zone: DELIVERY_ZONES[0],
  // {displayName, lat, lng} una vez geocodificada, o {skipped:true} si el
  // usuario decidió seguir sin dirección. `null`/`undefined` significa que
  // todavía no pasó por el onboarding, y es lo que dispara el modal.
  //
  // No se versionó la clave de localStorage al agregar este campo: los perfiles
  // guardados antes no lo tienen, así que quedan en undefined y ven el modal,
  // que es justo el comportamiento buscado.
  location: null,
  // Veredicto de cobertura por tienda para la dirección actual:
  // {coto_online: {covered, sucursal, message, checkedAt}}.
  //
  // Se guarda porque antes se consultaba en el onboarding y se tiraba, y el
  // catálogo seguía mostrando productos de una tienda que no entrega acá.
  //
  // Mismo criterio que `location`: la clave de localStorage no se versiona, así
  // que los perfiles viejos lo reciben `undefined` = "no sabemos" = no se filtra
  // nada (fail-open, igual que el backend).
  storeCoverage: {},
};

function stampCoverage(coverageByStore) {
  const now = Date.now();
  return Object.fromEntries(
    Object.entries(coverageByStore).map(([storeId, coverage]) => [
      storeId,
      { ...coverage, checkedAt: now },
    ])
  );
}

export function ProfileProvider({ children }) {
  const [profile, setProfile] = useLocalStorage(STORAGE_KEY, DEFAULT_PROFILE);

  function setCards(cards) {
    setProfile((prev) => ({ ...prev, cards }));
  }

  function setMemberships(memberships) {
    setProfile((prev) => ({ ...prev, memberships }));
  }

  function setZone(zone) {
    setProfile((prev) => ({ ...prev, zone }));
  }

  // La cobertura pertenece a una coordenada, así que cambiar de dirección la
  // invalida: se pisa junto con `location` en vez de arrastrar el veredicto de
  // la dirección anterior. Va como segundo argumento —y no como un setter
  // aparte— justamente para que sea imposible guardar una dirección nueva y
  // dejar sin querer la cobertura vieja.
  function setLocation(location, coverageByStore = {}) {
    setProfile((prev) => ({ ...prev, location, storeCoverage: stampCoverage(coverageByStore) }));
  }

  function skipLocation() {
    setProfile((prev) => ({ ...prev, location: { skipped: true }, storeCoverage: {} }));
  }

  function clearLocation() {
    setProfile((prev) => ({ ...prev, location: null, storeCoverage: {} }));
  }

  function setStoreCoverage(storeId, coverage) {
    setProfile((prev) => ({
      ...prev,
      storeCoverage: { ...(prev.storeCoverage || {}), [storeId]: { ...coverage, checkedAt: Date.now() } },
    }));
  }

  const deliveryCosts = useMemo(() => getDeliveryCostsForZone(profile.zone), [profile.zone]);

  // Coordenadas listas para mandar a POST /optimize, o null si el usuario
  // salteó el onboarding (en ese caso el backend cae a los costos por zona).
  const coordinates = useMemo(() => {
    const location = profile.location;
    if (!location || location.skipped) return null;
    if (typeof location.lat !== "number" || typeof location.lng !== "number") return null;
    return { lat: location.lat, lng: location.lng };
  }, [profile.location]);

  // Tiendas que hay que sacar del catálogo. Solo entra un `covered === false`
  // explícito: un `ok:false` del backend significa "no pudimos preguntar", y
  // tratarlo como "no entregan" borraría media góndola por un timeout ajeno.
  const unavailableStores = useMemo(() => {
    const coverage = profile.storeCoverage;
    if (!coverage) return NO_UNAVAILABLE_STORES;
    const ids = Object.entries(coverage)
      .filter(([, verdict]) => verdict?.covered === false)
      .map(([storeId]) => storeId);
    return ids.length > 0 ? ids : NO_UNAVAILABLE_STORES;
  }, [profile.storeCoverage]);

  const value = useMemo(
    () => ({
      ...profile,
      deliveryCosts,
      coordinates,
      unavailableStores,
      setCards,
      setMemberships,
      setZone,
      setLocation,
      setStoreCoverage,
      skipLocation,
      clearLocation,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [profile, deliveryCosts, coordinates, unavailableStores]
  );

  return <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>;
}

export function useProfile() {
  const ctx = useContext(ProfileContext);
  if (!ctx) throw new Error("useProfile debe usarse dentro de un ProfileProvider");
  return ctx;
}
