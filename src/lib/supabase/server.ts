import { createServerClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";
import { cookies } from "next/headers";

import { getServerEnv } from "@/lib/env";
import type { Database } from "@/types/database";

/**
 * Cookie-aware Supabase client for Server Components, Server Actions,
 * and Route Handlers. Subject to RLS — uses the anon key.
 *
 * Always pair with `supabase.auth.getUser()` (not `getSession()`) to
 * revalidate the session against Supabase Auth.
 */
export async function createClient(): Promise<SupabaseClient<Database>> {
  const env = getServerEnv();
  const cookieStore = await cookies();

  return createServerClient<Database>(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            );
          } catch {
            // setAll() called from a Server Component — refreshing cookies
            // there is not allowed. Safe to ignore: src/proxy.ts handles
            // session refresh on every request.
          }
        },
      },
    }
  );
}
