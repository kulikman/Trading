"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

interface AutoRefreshProps {
  intervalMs: number;
}

/** Повторный запрос данных страницы с сервера (интервал в мс — с бэкенда, §5). */
export function AutoRefresh({ intervalMs }: AutoRefreshProps): null {
  const router = useRouter();
  useEffect(() => {
    const timer = setInterval(() => router.refresh(), intervalMs);
    return () => clearInterval(timer);
  }, [router, intervalMs]);
  return null;
}
