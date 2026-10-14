"use client";

import { useState } from "react";

interface CopyButtonProps {
  text: string;
  label: string;
}

const COPIED_MS = 1500;

/** Копирует готовый текст (с бэкенда) в буфер обмена — например, ошибку для отправки на исправление. */
export function CopyButton({ text, label }: CopyButtonProps): React.ReactElement {
  const [isCopied, setIsCopied] = useState(false);

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), COPIED_MS);
    } catch (error) {
      console.error("Copy to clipboard failed:", error);
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      title={isCopied ? "Скопировано" : label}
      aria-label={isCopied ? "Скопировано" : label}
      className={`button inline-flex h-7 w-7 items-center justify-center !p-0 ${isCopied ? "tone-positive" : ""}`}
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        {isCopied ? (
          <path d="M20 6 9 17l-5-5" />
        ) : (
          <>
            <rect x="9" y="9" width="13" height="13" rx="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </>
        )}
      </svg>
    </button>
  );
}
