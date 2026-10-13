#!/usr/bin/env node
/**
 * If package.json is still the template slug, print a one-time-style hint to run
 * `pnpm post-clone`. Exits 0 always so `pnpm dev` is never blocked.
 *
 * @see README.md — «Быстрый старт»
 * Silence while working on the upstream template: TEMPLATE_DEV=1 pnpm dev
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "..");

if (
  process.env.TEMPLATE_DEV === "1" ||
  process.env.SKIP_TEMPLATE_RENAME_REMINDER === "1"
) {
  process.exit(0);
}

let name = "";
try {
  const raw = readFileSync(join(root, "package.json"), "utf8");
  name = JSON.parse(raw).name;
} catch {
  process.exit(0);
}

if (name !== "template-projects") {
  process.exit(0);
}

// stderr so the message stays visible above Turbopack logs
console.warn(`
┌─────────────────────────────────────────────────────────────────────
│  Шаблон: package.json ещё «template-projects» (Template-Projects)
│  Переименуйте под продукт (отображаемое имя, slug, продакшен-URL):
│    pnpm post-clone "Мой продукт" "my-product" "https://myproduct.com"
│  Разрабатываете сам шаблон?  TEMPLATE_DEV=1 pnpm dev — без этого текста
└─────────────────────────────────────────────────────────────────────
`);

process.exit(0);
