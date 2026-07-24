import { AlertTriangle } from "lucide-react";

export function InfeasibleNotice({ detail }) {
  return (
    <div className="flex gap-2 rounded-md border border-state-warning/40 bg-state-warning/10 p-4 text-sm text-state-warning">
      <AlertTriangle size={18} className="mt-0.5 shrink-0" />
      <p>{detail}</p>
    </div>
  );
}
