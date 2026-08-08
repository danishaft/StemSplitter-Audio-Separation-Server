import createClient from "openapi-fetch";

import type { paths } from "./schema";


const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL;
const apiBaseUrl = (configuredBaseUrl || (import.meta.env.DEV ? "/api" : "")).replace(/\/$/, "");

export const api = createClient<paths>({ baseUrl: apiBaseUrl });

export type GetAccessToken = () => Promise<string | null>;

export function apiPath(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${apiBaseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function authHeaders(
  getToken: GetAccessToken
): Promise<Record<string, string>> {
  const token = await getToken();
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
