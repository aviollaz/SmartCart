import { apiFetch } from "./client";

export function searchProducts(query, limit = 20) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  return apiFetch(`/search?${params.toString()}`);
}

export function getProductsByCategory(categoryName, limit = 50) {
  const params = new URLSearchParams({ limit: String(limit) });
  return apiFetch(`/category/${encodeURIComponent(categoryName)}?${params.toString()}`);
}
