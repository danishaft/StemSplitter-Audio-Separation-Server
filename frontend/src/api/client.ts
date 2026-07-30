import createClient from "openapi-fetch";

import type { paths } from "./schema";


const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export const api = createClient<paths>({ baseUrl: apiBaseUrl });

export function apiPath(path: string): string {
  return `${apiBaseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

export function authHeaders(): Record<string, string> {
  const token = window.localStorage.getItem("stemsplitter_access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function apiError(error: unknown, response: Response): Error {
  if (error && typeof error === "object") {
    const payload = error as { error?: string; message?: string };
    return new Error(
      payload.message || payload.error || `Request failed (${response.status})`
    );
  }
  return new Error(`Request failed (${response.status})`);
}
