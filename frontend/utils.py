# frontend/utils.py
import requests
import streamlit as st

API_URL = "http://localhost:8000"

@st.cache_data(ttl=300)
def search_products(query: str, limit: int = 20):
    """Llama al endpoint GET /search de FastAPI."""
    try:
        response = requests.get(f"{API_URL}/search", params={"q": query, "limit": limit})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error conectando al backend (Búsqueda): {e}")
        return []

def optimize_cart(cart_items: list, memberships: list, cards: list, delivery_costs: dict):
    """Llama al endpoint POST /optimize de FastAPI."""
    payload = {
        "cart": cart_items,
        "user_memberships": memberships,
        "user_cards": cards,
        "delivery_costs": delivery_costs
    }
    try:
        response = requests.post(f"{API_URL}/optimize", json=payload)
        
        # Manejo específico para cuando el solver no encuentra solución (HTTP 400)
        if response.status_code == 400:
            st.warning(f"El optimizador respondió: {response.json().get('detail')}")
            return None
            
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error conectando al backend (Optimizador): {e}")
        return None

@st.cache_data(ttl=3600)
def get_categories():
    """Llama al endpoint GET /categories."""
    try:
        response = requests.get(f"{API_URL}/categories")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return []

@st.cache_data(ttl=300)
def search_by_category(category_name: str):
    """Llama al endpoint GET /category/{category_name}."""
    try:
        response = requests.get(f"{API_URL}/category/{category_name}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error conectando al backend (Categorías): {e}")
        return []