import { useHistory } from "../../context/HistoryContext";
import { ConfirmClearButton } from "../common/ConfirmClearButton";

/**
 * Borrar el historial de compras, con confirmación en dos pasos in-place.
 *
 * Existe porque el historial es lo más parecido a un dato personal que guarda la
 * app: tiene que poder borrarse de un click, sin buscarlo en un menú.
 *
 * No hay borrado por entrada a propósito: es más UI y más estado, y el usuario no
 * puede ver el efecto de lo que estaría editando (el ranking).
 */
export function ClearHistoryButton({ className = "" }) {
  const { entries, clearHistory } = useHistory();

  return (
    <ConfirmClearButton
      count={entries.length}
      idleLabel="Borrar historial"
      confirmQuestion={(count) =>
        `¿Borrar ${count === 1 ? "la única compra guardada" : `las ${count} compras guardadas`}?`
      }
      confirmLabel="Sí, borrar"
      onConfirm={clearHistory}
      className={className}
    />
  );
}
