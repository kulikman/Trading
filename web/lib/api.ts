import "server-only";

import { connection } from "next/server";

// Запросы к API дашборда — только с сервера (DASHBOARD.md §7): токен в браузер не попадает.
const DEFAULT_API_URL = "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
  ) {
    super(`API ${status} on ${path}`);
  }
}

/** GET к API дашборда; данные свежие на каждый запрос (без кэша). */
export async function apiGet<T>(path: string): Promise<T> {
  await connection(); // только во время запроса: при сборке API нет, токена тоже
  const token = process.env.DASHBOARD_API_TOKEN;
  if (!token) {
    throw new Error("DASHBOARD_API_TOKEN is not set");
  }
  const base = process.env.DASHBOARD_API_URL ?? DEFAULT_API_URL;
  const response = await fetch(`${base}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiError(response.status, path);
  }
  return (await response.json()) as T;
}

/** То же, но 404 → null (нет такой сделки, сектора, компании). */
export async function apiGetOrNull<T>(path: string): Promise<T | null> {
  try {
    return await apiGet<T>(path);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}
