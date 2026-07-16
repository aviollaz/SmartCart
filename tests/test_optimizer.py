# tests/test_optimizer.py
import json
from src.optimizer import optimize_cart

def test_optimization_with_minimum_spend():
    # Carrito de compras
    cart = [
        {"unified_id": "prod_7798359560445", "quantity": 3},  # Alfajor Marley
        {"unified_id": "prod_7792180145406", "quantity": 10}  # Alfajor 9 de Oro
    ]

    # Mínimos de compra bajos para facilitar que se usen ambos súper
    min_spend = {
        "coto_online": 500,
        "dia_online": 500
    }

    # Costos de envío ficticios
    delivery = {
        "coto_online": 3000,
        "dia_online": 3000
    }

    # El usuario cuenta con Tarjeta Galicia
    user_cards = ["galicia"]

    result = optimize_cart(
        cart, 
        user_memberships=["club_dia"], 
        user_cards=user_cards,
        min_spend_limits=min_spend,
        delivery_costs=delivery
    )

    print("\n" + "=" * 60)
    print("🧠 DEVOLUCIÓN DE OR-TOOLS (CON ENVÍO Y TARJETAS)")
    print("=" * 60)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("=" * 60 + "\n")

    assert "status" in result
    if result["status"] == "success":
        assert result["total_spent_net"] > 0