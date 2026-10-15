import Link from "next/link";

/** Русская 404 (аудит дашборда 14.10.2026): нет такой сделки, компании или страницы. */
export default function NotFound(): React.ReactElement {
  return (
    <section className="mt-8">
      <h2>Страница не найдена</h2>
      <p className="muted">Такой сделки, компании или раздела нет.</p>
      <p>
        <Link href="/">На «Сегодня»</Link>
      </p>
    </section>
  );
}
