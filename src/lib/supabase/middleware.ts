import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { getServerEnv } from "@/lib/env";
import type { Database } from "@/types/database";

/**
 * Refreshes the Supabase auth session on every matched request.
 *
 * Called from src/proxy.ts. Without this, sessions in server components
 * become stale after ~1 hour and RLS-protected queries start failing.
 *
 * Pattern taken from @supabase/ssr official docs — do not refactor without
 * reading their migration notes first.
 */
export async function updateSession(request: NextRequest): Promise<NextResponse> {
  const env = getServerEnv();
  let response = NextResponse.next({ request });

  const supabase = createServerClient<Database>(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => {
            request.cookies.set(name, value);
          });
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) => {
            response.cookies.set(name, value, options);
          });
        },
      },
    }
  );

  // IMPORTANT: getUser() (not getSession()) revalidates with Supabase Auth.
  // getSession() only reads the cookie — which may be stale or forged.
  await supabase.auth.getUser();

  return response;
}
