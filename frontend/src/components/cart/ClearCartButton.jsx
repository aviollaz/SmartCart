import { useCart } from "../../context/CartContext";
import { ConfirmClearButton } from "../common/ConfirmClearButton";

/**
 * Vaciar el carrito, con confirmación en dos pasos in-place.
 *
 * Se conecta solo al contexto (cuenta los ítems y llama a clear), así los dos
 * lugares que lo montan — la página del carrito y el drawer — no cablean nada.
 */
export function ClearCartButton({ className = "" }) {
  const { itemCount, clear } = useCart();

  return (
    <ConfirmClearButton
      count={itemCount}
      idleLabel="Vaciar carrito"
      confirmQuestion={(count) =>
        `¿Vaciar ${count === 1 ? "el único producto" : `los ${count} productos`}?`
      }
      confirmLabel="Sí, vaciar"
      onConfirm={clear}
      className={className}
    />
  );
}
