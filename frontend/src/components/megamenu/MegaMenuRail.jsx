import { getTopLevelIcon } from "./topLevelIcons";

export function MegaMenuRail({ topLevels, activeLabel, onHover }) {
  return (
    <ul className="w-64 shrink-0 overflow-y-auto bg-brand-violet-700 py-2 text-white">
      {topLevels.map((node) => {
        const Icon = getTopLevelIcon(node.label);
        const isActive = node.label === activeLabel;
        return (
          <li key={node.label}>
            <button
              type="button"
              onMouseEnter={() => onHover(node.label)}
              onFocus={() => onHover(node.label)}
              className={`flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors ${
                isActive ? "bg-brand-violet-900" : "hover:bg-brand-violet-500"
              }`}
            >
              <Icon size={18} className="shrink-0" aria-hidden="true" />
              <span className="truncate">{node.label}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
