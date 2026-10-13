import "server-only";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { getServerEnv } from "@/lib/env";
import type { Database } from "@/types/database";

/**
 * Service-role Supabase client. **Bypasses RLS.**
 *
 * Use only in trusted server contexts: Edge Functions, webhooks,
 * scheduled jobs, admin scripts. Never call from a `"use client"` file
 * — `import "server-only"` will fail the build if you do.
 */
export function createAdminClient(): SupabaseClient<Database> {
  const env = getServerEnv();
  return createClient<Database>(env.NEXT_PUBLIC_SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY, {
    auth: {
      autoRefreshToken: false,
      persistSession: false,
    },
  });
}
