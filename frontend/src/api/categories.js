import { apiFetch } from "./client";

export function getCategories() {
  return apiFetch("/categories");
}

export function getCategoryTree() {
  return apiFetch("/categories/tree");
}
