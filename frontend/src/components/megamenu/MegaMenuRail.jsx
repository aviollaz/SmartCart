import { getSectionIcon } from "./sectionIcons";

export function MegaMenuRail({ sections, activeSection, onHover }) {
  return (
    <ul className="flex w-full shrink-0 overflow-x-auto bg-brand-violet-700 py-2 text-white md:w-64 md:flex-col md:overflow-x-visible md:overflow-y-auto">
      {sections.map((node) => {
        const Icon = getSectionIcon(node.section);
        const isActive = node.section === activeSection;
        return (
          <li key={node.section} className="shrink-0 md:shrink">
            <button
              type="button"
              // `onClick` además del hover: en un touchscreen no hay hover, así
              // que el menú dependía de que el tap generara focus. Funciona por
              // accidente, no por diseño.
              onClick={() => onHover(node.section)}
              onMouseEnter={() => onHover(node.section)}
              onFocus={() => onHover(node.section)}
              className={`flex w-full items-center gap-2 whitespace-nowrap px-4 py-2.5 text-left text-sm transition-colors md:gap-3 ${
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
