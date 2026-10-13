import "server-only";

import { createAdminClient } from "@/lib/supabase/admin";
import { hashApiKey } from "../lib/crypto";

/**
 * Authenticate an incoming API request by looking up the hashed key.
 * Call this from trusted server Route Handlers that support API key auth.
 *
 * Uses the service-role client because external API-key requests do not have a
 * Supabase auth cookie, so RLS-bound user clients cannot look up the key hash.
 *
 * @example
 * @public
 *
 *   const userId = await verifyApiKey(request.headers.get("x-api-key"))
 *   if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 })
 */
export async function verifyApiKey(rawKey: string | null): Promise<string | null> {
  if (!rawKey) return null;

  const hash = await hashApiKey(rawKey);
  const supabase = createAdminClient();

  const { data } = await supabase
    .from("api_keys")
    .select("user_id, expires_at")
    .eq("key_hash", hash)
    .maybeSingle();

  if (!data) return null;
  if (data.expires_at && new Date(data.expires_at).getTime() <= Date.now()) return null;

  // Fire-and-forget: update last_used_at without blocking the API response.
  void supabase
    .from("api_keys")
    .update({ last_used_at: new Date().toISOString() })
    .eq("key_hash", hash);

  return data.user_id;
}
