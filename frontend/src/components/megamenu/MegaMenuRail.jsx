import { getSectionIcon } from "./sectionIcons";

export function MegaMenuRail({ sections, activeSection, onHover }) {
  return (
    <ul className="w-64 shrink-0 overflow-y-auto bg-brand-violet-700 py-2 text-white">
      {sections.map((node) => {
        const Icon = getSectionIcon(node.section);
        const isActive = node.section === activeSection;
        return (
          <li key={node.section}>
            <button
              type="button"
              onMouseEnter={() => onHover(node.section)}
              onFocus={() => onHover(node.section)}
              className={`flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors ${
                isActive ? "bg-brand-violet-900" : "hover:bg-brand-violet-500"
              }`}
            >
              <Icon size={18} className="shrink-0" aria-hidden="true" />
              <span className="truncate">{node.section}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
