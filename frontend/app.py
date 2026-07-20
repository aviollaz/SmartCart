# frontend/app.py
import streamlit as st
from utils import search_products, optimize_cart, get_categories, search_by_category

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="SmartCart AR", page_icon="🛒", layout="wide")
st.title("🛒 SmartCart Argentina")
st.markdown("Motor de optimización de compras y búsqueda semántica.")

# --- MANEJO DE ESTADO (SESSION STATE) ---
# Guardamos el carrito como un diccionario {unified_id: {"name": str, "quantity": int}}
if "cart" not in st.session_state:
    st.session_state.cart = {}

# --- BARRA LATERAL: CONFIGURACIÓN DEL USUARIO ---
with st.sidebar:
    st.header("⚙️ Tu Perfil")
    
    st.subheader("Medios de Pago y Fidelidad")
    user_cards = st.multiselect(
        "Tarjetas Bancarias", 
        ["galicia", "macro", "nacion", "bbva", "mercado_pago"],
        help="Seleccioná las tarjetas que tenés para calcular reintegros."
    )
    user_memberships = st.multiselect(
        "Membresías de Supermercados", 
        ["club_dia", "coto_tci", "comunidad_coto", "jumbo_mas"]
    )
    
    st.subheader("Ubicación (Envío)")
    # Mapeo simple de zonas a costos de envío para pasarlo al backend
    zona_envio = st.selectbox("Seleccioná tu zona", ["CABA", "GBA Norte", "GBA Sur", "GBA Oeste"])
    
    # Costos ficticios dinámicos según la zona
    delivery_mock = {
        "CABA": {"coto_online": 2500.0, "dia_online": 2000.0},
        "GBA Norte": {"coto_online": 3500.0, "dia_online": 3000.0},
        "GBA Sur": {"coto_online": 4000.0, "dia_online": 4000.0},
        "GBA Oeste": {"coto_online": 3800.0, "dia_online": 3500.0},
    }
    current_delivery_costs = delivery_mock[zona_envio]

# --- ÁREA PRINCIPAL: PESTAÑAS ---
tab1, tab2 = st.tabs(["🔍 Búsqueda de Productos", f"🛒 Mi Carrito ({len(st.session_state.cart)} items)"])

# --- PESTAÑA 1: BÚSQUEDA ---
with tab1:
    search_mode = st.radio("Modo de exploración", ["Búsqueda Libre (Semántica)", "Navegar por Categorías"], horizontal=True)
    results = []

    if search_mode == "Búsqueda Libre (Semántica)":
        query = st.text_input("¿Qué estás buscando?", placeholder="Ej: puré de papas, alfajor de chocolate...")
        if query:
            with st.spinner("Buscando similitudes semánticas..."):
                results = search_products(query)
                
    else:
        # Modo Categorías
        categories = get_categories()
        if not categories:
            st.warning("No se encontraron categorías en la base de datos.")
        else:
            selected_cat = st.selectbox("Seleccioná una categoría:", categories)
            if selected_cat:
                with st.spinner(f"Cargando productos de {selected_cat}..."):
                    results = search_by_category(selected_cat)

    # Renderizado de productos (común para ambos métodos)
    if not results and (search_mode == "Navegar por Categorías" or ('query' in locals() and query)):
        st.info("No se encontraron productos.")
    else:
        for prod in results:
            # Armamos el título con el precio base más bajo
            min_price = prod.get("min_price", 0.0)
            price_label = f" — Desde ${min_price:,.2f}" if min_price > 0 else ""
            
            with st.expander(f"📦 {prod['name']} ({prod['brand']}){price_label}"):
                # 3 columnas: Imagen, Info, Botón
                col_img, col_info, col_btn = st.columns([1.5, 3, 1.5])
                
                with col_img:
                    img_url = prod.get('image_url')
                    if img_url:
                        st.image(img_url, use_container_width=True)
                    else:
                        st.info("📷 Sin foto")
                
                with col_info:
                    st.write(f"**Categoría:** `{prod.get('category', 'N/A')}`")
                    if prod['available_at_stores']:
                        # Mostrar desglose rápido de ofertas
                        for store in prod['available_at_stores']:
                            store_name = store['store_id'].replace('_online', '').upper()
                            st.write(f"🏪 **{store_name}:** ${store['base_price']:,.2f}")
                    else:
                        st.warning("Sin stock registrado.")
                
                with col_btn:
                    if st.button("Sumar al chango", key=f"add_{prod['unified_id']}"):
                        uid = prod['unified_id']
                        if uid in st.session_state.cart:
                            st.session_state.cart[uid]["quantity"] += 1
                        else:
                            st.session_state.cart[uid] = {"name": prod['name'], "quantity": 1}
                        st.rerun()

# --- PESTAÑA 2: CARRITO Y OPTIMIZADOR ---
with tab2:
    if not st.session_state.cart:
        st.info("Tu carrito está vacío. Buscá productos en la pestaña de al lado.")
    else:
        st.subheader("Productos Seleccionados")
        
        # Mostramos los items del carrito con opción de sumar/restar o eliminar
        for uid, data in list(st.session_state.cart.items()):
            colA, colB, colC, colD = st.columns([4, 1, 1, 1])
            colA.write(f"**{data['name']}**")
            colB.write(f"Cant: {data['quantity']}")
            
            if colC.button("➕", key=f"plus_{uid}"):
                st.session_state.cart[uid]["quantity"] += 1
                st.rerun()
                
            if colD.button("🗑️", key=f"del_{uid}"):
                del st.session_state.cart[uid]
                st.rerun()

        st.divider()
        
        # Botón de Optimización
        if st.button("🚀 Optimizar Compra con OR-Tools", type="primary", use_container_width=True):
            # Adaptamos el diccionario local al formato de lista que espera la API
            cart_payload = [{"unified_id": uid, "quantity": data["quantity"]} for uid, data in st.session_state.cart.items()]
            
            with st.spinner("Corriendo solver CP-SAT..."):
                result = optimize_cart(
                    cart_items=cart_payload,
                    memberships=user_memberships,
                    cards=user_cards,
                    delivery_costs=current_delivery_costs
                )
            
            if result and result.get("status") == "success":
                st.success("¡Asignación óptima encontrada!")
                st.metric("Gasto Total Neto Proyectado", f"${result['total_spent_net']:,.2f}")
                
                st.subheader("📦 Desglose por Supermercado")
                split_data = result.get("split", {})
                
                # Creamos columnas según la cantidad de supermercados elegidos por el solver
                cols = st.columns(len(split_data)) if split_data else [st.container()]
                
                for idx, (store_id, checkout) in enumerate(split_data.items()):
                    with cols[idx]:
                        st.info(f"**{store_id.upper()}**")
                        st.write(f"**Subtotal Productos:** ${checkout['subtotal_products']:,.2f}")
                        st.write(f"**Costo de Envío:** ${checkout['delivery_cost']:,.2f}")
                        
                        if checkout.get('bank_discount'):
                            bd = checkout['bank_discount']
                            # Intentamos varios nombres comunes de la clave, o ponemos un texto por defecto
                            desc = bd.get('promo_description', bd.get('description', bd.get('name', 'Descuento Bancario Aplicado')))
                            
                            # Hacemos lo mismo para el monto (por si se llama 'amount', 'discount_total', etc.)
                            amount = bd.get('discount_amount', bd.get('amount', bd.get('discount_total', bd.get('value', 0.0))))
                            
                            st.success(f"💳 {desc}: -${amount:,.2f}")
                        
                        st.write(f"### Total Tienda: ${checkout['store_total']:,.2f}")
                        
                        # Lista de productos a comprar acá
                        with st.expander("Ver lista para esta tienda"):
                            for item in checkout['products']:
                                name = st.session_state.cart[item['unified_id']]['name']
                                st.write(f"- {name} (x{item['quantity']})")