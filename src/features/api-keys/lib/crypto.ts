/**
 * Cryptographic utilities for API key generation and hashing.
 *
 * - Keys are generated with the Web Crypto API (available in Node 16+ and all browsers).
 * - Only the SHA-256 hash is persisted; the raw key is shown once and then discarded.
 * - Format: `sk_live_<32 random hex chars>` (64 chars total, easy to spot in logs).
 */

/** Generate a new random API key. */
export function generateApiKey(): string {
  const bytes = new Uint8Array(20);
  crypto.getRandomValues(bytes);
  const hex = Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return `sk_live_${hex}`;
}

/** SHA-256 hash of the raw key (hex string). */
export async function hashApiKey(rawKey: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(rawKey);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** First 12 chars of the raw key — shown in the UI as "sk_live_ab12…" */
export function keyPrefix(rawKey: string): string {
  return rawKey.slice(0, 12);
}
