# SmartCart

Motor de recomendación y optimización de canastas de compra para supermercados argentinos (Coto y Día), que calcula la combinación de tiendas que minimiza el gasto total de una lista de compras.

Ver la especificación técnica completa en [`docs/smartcart_spec.md`](docs/smartcart_spec.md).

## Arquitectura

- **Backend** (`src/`): FastAPI + PostgreSQL/pgvector. Búsqueda semántica de productos, catálogo unificado por EAN, optimizador de canasta con Google OR-Tools, scrapers de Coto y Día.
- **Frontend** (`frontend/`): React + Vite + Tailwind CSS. Header y mega-menú de categorías estilo e-commerce, grilla de productos con filtros, carrito y flujo de optimización.

## Cómo correrlo localmente

### 1. Base de datos

```bash
docker-compose up -d
```

Levanta Postgres con la extensión `pgvector` en `localhost:5432` (usuario/clave/DB: `smartuser`/`smartpassword`/`smartcart`).

### 2. Backend

```bash
pip install -r requirements.txt
uvicorn src.api:app --reload
```

La API queda disponible en `http://localhost:8000` (docs interactivas en `/docs`).

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

La app queda disponible en `http://localhost:5173` (configurable vía `frontend/.env`, variable `VITE_API_URL`).

### Tests

```bash
pytest
```
