import { Range } from "react-range";
import { formatPrice } from "../../utils/formatters";

export function PriceRangeSlider({ bounds, value, onChange }) {
  const [min, max] = bounds;

  if (min >= max) return null;

  return (
    <div className="border-b border-line py-4">
      <p className="mb-3 font-display text-sm font-semibold text-ink">Gama de precios</p>
      <Range
        min={min}
        max={max}
        step={Math.max(1, Math.round((max - min) / 100))}
        values={value}
        onChange={onChange}
        renderTrack={({ props, children }) => (
          <div {...props} className="h-1.5 w-full rounded-full bg-line" style={props.style}>
            {children}
          </div>
        )}
        renderThumb={({ props }) => {
          const { key, ...thumbProps } = props;
          return (
            <div
              key={key}
              {...thumbProps}
              className="h-4 w-4 rounded-full bg-brand-violet-700 shadow"
              style={thumbProps.style}
            />
          );
        }}
      />
      <div className="mt-2 flex justify-between text-xs text-ink-muted">
        <span>{formatPrice(value[0])}</span>
        <span>{formatPrice(value[1])}</span>
      </div>
    </div>
  );
}
