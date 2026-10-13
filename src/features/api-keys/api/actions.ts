"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { generateApiKey, hashApiKey, keyPrefix } from "../lib/crypto";

export interface CreateApiKeyResult {
  /** The full raw key — shown ONCE, not stored. */
  rawKey: string;
  /** The persisted key record ID. */
  id: string;
}

/**
 * Create a new API key for the current user.
 * Returns the raw key — it must be shown to the user immediately.
 * After this call the raw key cannot be recovered.
 */
export async function createApiKey(name: string): Promise<CreateApiKeyResult> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const rawKey = generateApiKey();
  const hash = await hashApiKey(rawKey);
  const prefix = keyPrefix(rawKey);

  const { data, error } = await supabase
    .from("api_keys")
    .insert({
      user_id: user.id,
      name: name.trim(),
      key_hash: hash,
      key_prefix: prefix,
    })
    .select("id")
    .single();

  if (error) throw new Error(error.message);

  revalidatePath("/settings/api-keys");

  return { rawKey, id: data.id };
}

/**
 * Delete an API key by ID.
 * RLS ensures users can only delete their own keys.
 */
export async function deleteApiKey(keyId: string): Promise<void> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  await supabase.from("api_keys").delete().eq("id", keyId).eq("user_id", user.id);

  revalidatePath("/settings/api-keys");
}

/**
 * Rename an existing API key.
 *
 * @public
 */
export async function renameApiKey(keyId: string, newName: string): Promise<void> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  await supabase
    .from("api_keys")
    .update({ name: newName.trim() })
    .eq("id", keyId)
    .eq("user_id", user.id);

  revalidatePath("/settings/api-keys");
}
