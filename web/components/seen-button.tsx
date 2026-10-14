"use client";

import { useRouter } from "next/navigation";

export const SEEN_COOKIE = "changes_seen_at";

/** «Понятно» — запомнить момент просмотра; блок ИЗМЕНИЛОСЬ покажет только новое (§4.1). */
export function SeenButton(): React.ReactElement {
  const router = useRouter();
  return (
    <button
      type="button"
      className="button"
      onClick={() => {
        document.cookie = `${SEEN_COOKIE}=${new Date().toISOString()}; path=/; max-age=31536000; samesite=lax`;
        router.refresh();
      }}
    >
      понятно
    </button>
  );
}
