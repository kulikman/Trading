"use client";

import { useEffect, useState } from "react";

/**
 * Returns `true` after the component has mounted on the client.
 *
 * Use to avoid hydration mismatches when rendering something that differs
 * between SSR and the client (e.g., reading `window`, `localStorage`, or
 * user theme).
 *
 * @example
 *   const mounted = useMounted()
 *   if (!mounted) return null
 *   return <ClientOnlyThing />
 */
export function useMounted(): boolean {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    queueMicrotask(() => {
      setMounted(true);
    });
  }, []);

  return mounted;
}
