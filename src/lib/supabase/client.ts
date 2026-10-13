import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

import { getClientEnv } from "@/lib/env";
import type { Database } from "@/types/database";

/**
 * Browser-side Supabase client. Subject to RLS via the anon key.
 * Use only inside `"use client"` components or browser-only hooks.
 */
export function createClient(): SupabaseClient<Database> {
  const env = getClientEnv();
  return createBrowserClient<Database>(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  );
}
