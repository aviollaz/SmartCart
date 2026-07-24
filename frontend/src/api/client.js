const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    let detail = null;
    try {
      detail = (await response.json()).detail;
    } catch {
      // el cuerpo del error no era JSON, seguimos sin detail
    }
    throw new ApiError(
      `Error ${response.status} al llamar a ${path}`,
      response.status,
      detail
    );
  }

  if (response.status === 204) return null;
  return response.json();
}
