import "server-only";

import { headers } from "next/headers";

interface HeaderReader {
  get(name: string): string | null;
}

export function getClientIpFromHeaders(headersList: HeaderReader): string {
  return (
    headersList.get("x-forwarded-for")?.split(",")[0]?.trim() ??
    headersList.get("x-real-ip") ??
    "unknown"
  );
}

export async function getRequestIp(): Promise<string> {
  return getClientIpFromHeaders(await headers());
}
