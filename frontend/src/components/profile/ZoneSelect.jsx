import { DELIVERY_ZONES } from "../../utils/deliveryCosts";

export function ZoneSelect({ zone, onChange }) {
  return (
    <label className="block text-sm text-ink">
      <span className="mb-2 block font-semibold">Zona de envío</span>
      <select
        value={zone}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
      >
        {DELIVERY_ZONES.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}
