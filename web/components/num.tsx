import type { Num as NumValue, Tone } from "@/lib/types";

const TONE_CLASS: Record<Tone, string> = {
  positive: "tone-positive",
  negative: "tone-negative",
  action: "tone-action",
  neutral: "",
};

/** Класс цвета по полю tone с бэкенда (DASHBOARD.md §5). */
export function toneClass(tone: Tone): string {
  return TONE_CLASS[tone];
}

interface NumProps {
  value: NumValue | null;
}

/** Число с бэкенда: показывается только display, цвет — по tone. */
export function N({ value }: NumProps): React.ReactElement {
  if (value === null) {
    return <span className="muted">—</span>;
  }
  return <span className={`num ${toneClass(value.tone)}`}>{value.display}</span>;
}
