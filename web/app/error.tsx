"use client";

/** Русская страница ошибки (аудит дашборда 14.10.2026, DASHBOARD §6: сбой — «СБОЙ» красным). */
export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}): React.ReactElement {
  const isApi = error.message.startsWith("API ") || error.message.includes("fetch failed");
  return (
    <section className="mt-8">
      <h2 className="tone-negative">{isApi ? "СИСТЕМА: СБОЙ API" : "СИСТЕМА: СБОЙ"}</h2>
      <p className="muted">
        {isApi
          ? "Сервер данных не ответил. Обычно это проходит за минуту."
          : "Страница не открылась из-за ошибки."}
        {error.digest ? ` Код для поддержки: ${error.digest}.` : ""}
      </p>
      <button type="button" className="tab" onClick={reset}>
        Повторить
      </button>
    </section>
  );
}
