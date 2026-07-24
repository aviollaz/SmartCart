import { createContext, useContext, useMemo } from "react";
import { useLocalStorage } from "../hooks/useLocalStorage";
import { DELIVERY_ZONES, getDeliveryCostsForZone } from "../utils/deliveryCosts";

const ProfileContext = createContext(null);

const STORAGE_KEY = "smartcart_profile_v1";

const DEFAULT_PROFILE = {
  cards: [],
  memberships: [],
  zone: DELIVERY_ZONES[0],
};

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

  const deliveryCosts = useMemo(() => getDeliveryCostsForZone(profile.zone), [profile.zone]);

  const value = useMemo(
    () => ({ ...profile, deliveryCosts, setCards, setMemberships, setZone }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [profile, deliveryCosts]
  );

  return <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>;
}

export function useProfile() {
  const ctx = useContext(ProfileContext);
  if (!ctx) throw new Error("useProfile debe usarse dentro de un ProfileProvider");
  return ctx;
}
