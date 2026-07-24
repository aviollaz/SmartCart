import { useEffect, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Mic, Search } from "lucide-react";

export function SearchBar({ className = "" }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [value, setValue] = useState("");

  useEffect(() => {
    if (location.pathname === "/buscar") {
      setValue(searchParams.get("q") || "");
    }
  }, [location.pathname, searchParams]);

  function handleSubmit(event) {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    navigate(`/buscar?q=${encodeURIComponent(trimmed)}`);
  }

  return (
    <form onSubmit={handleSubmit} className={`flex w-full max-w-2xl items-stretch ${className}`}>
      <div className="flex flex-1 items-center rounded-l-md border border-line bg-surface px-4">
        <input
          type="text"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="¿Qué estás buscando hoy?"
          className="w-full py-2.5 text-sm text-ink placeholder:text-ink-muted focus:outline-none"
        />
        <Mic size={18} className="shrink-0 text-ink-muted" aria-hidden="true" />
      </div>
      <button
        type="submit"
        aria-label="Buscar"
        className="flex items-center justify-center rounded-r-md bg-brand-accent px-4 text-white transition-colors hover:bg-brand-accent-dark"
      >
        <Search size={20} />
      </button>
    </form>
  );
}
