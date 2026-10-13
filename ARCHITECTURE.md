# Architecture — Service isolation

**TL;DR:** Each module is a black box with a public contract. From outside, only `index.ts` (the barrel for that feature) is the entry point. Inside the module, structure is yours. **Do not modify other modules’ internals.**

Full AI-agent checklist: see **§0** below. Enforcement: `eslint.config.mjs` (boundaries + restricted imports), `ARCHITECTURE.md`, `.cursor/rules/architecture.mdc`.

**Template note:** Generated DB types live at `src/types/database.ts` (not under `src/shared/`). Treat that file as read-only unless regenerating types.

---

## 0. AI assistant rules (read first)

Mandatory for Claude, Cursor, Codex, Copilot, and any LLM agent.

1. **Work in one module per task.** If the change spans 2+ modules, split into separate PRs/commits.
2. **Never edit another module’s `index.ts`** without explicit user instruction.
3. **Do not import from another module’s internal paths**, for example:
   - forbidden: `@/features/leads/lib/...`, `@/features/leads/api/queries`
   - forbidden: relative `../../other-feature/...`
   - allowed: `@/features/leads` only (barrel / public API)
4. If you need a symbol that is **not** re-exported from the owner’s `index.ts`, stop and say: *«The public API of module X must be extended. Requesting approval.»*
5. **Before editing**, read that module’s `index.ts` and note its public contract.
6. **After editing**, ensure public export signatures did not change unintentionally.
7. **Protected (do not touch without a direct command):**
   - `src/types/database.ts` (generated)
   - another module’s `index.ts`
   - another module’s DB migrations
   - `.env*`, secrets, CI secrets
8. **Before commit**, answer:
   - Did I break a public contract?
   - Did I touch files outside my module?
   - Did tests still pass?

   If any answer is *yes* where it should not be, stop and reconsider.

---

## 1. Core principle

Each service / feature is an **isolated unit** with a public contract.

Code outside a module **must not**:

- depend on internal layout
- read/write another module’s tables directly
- import internal files of another module

Internal refactors must not break other modules.

---

## 2. Bounded context

Each module owns:

- **Domain models** — types, schemas, enums
- **Data layer** — tables, queries, migrations (one owning module per table)
- **Business logic** — Server Actions, services, use-cases
- **Public API** — whatever `index.ts` re-exports

Suggested layout:

```text
src/features/[domain]/
├── index.ts          ← only external entry point
├── api/              ← Server Actions, handlers (private to the feature)
├── components/
├── types/
├── schemas/
├── hooks/
├── lib/              ← private; no imports from outside via @/features/.../lib
└── _internal/        ← optional alias for private code
```

---

## 3. Public API contract

Allowed:

```ts
import { createLead, type Lead } from "@/features/leads";
import { Button } from "@/components/ui/button";
```

Forbidden:

```ts
import { internalHelper } from "@/features/leads/lib/helper";
import { rawQuery } from "@/features/finance/api/queries";
import { something } from "../../leads/lib/utils";
```

Cross-feature access goes **only** through `@/features/[name]` (after you register the alias in `tsconfig.json`; see §7.2).

---

## 4. No shared mutable state

No shared in-memory globals between modules for business state. Prefer public APIs, events, or the database through each owner’s data layer.

---

## 5. Database ownership

**One table — one owning module.** Other modules call the owner’s public functions (for example `getLeadById`), not raw SQL against foreign tables. Document rare read-only analytics views in this file when you add them.

---

## 6. Change rules

| Change | Rule |
|--------|------|
| Inside your module | Allowed if the public API stays compatible |
| Your module’s public API | Prefer deprecate → migrate → remove |
| Someone else’s module | Do not edit; ask to extend their public API |

---

## 7. Enforcement (this repo)

### 7.1 Cursor

See `.cursor/rules/architecture.mdc` (always on for `*.ts` / `*.tsx`). Full narrative: this file.

### 7.2 TypeScript path aliases (`tsconfig.json`)

- `@/*` → `./src/*` (existing app layout: `components`, `lib`, `app`, …).
- `@/shared/*` → `./src/shared/*` (optional; create the folder when you introduce a shared kernel).
- For each feature, add a **file** alias to its barrel (not a folder glob), for example:

```json
"@/features/leads": ["./src/features/leads/index.ts"]
```

Deep paths such as `@/features/leads/lib/...` must not be added as aliases.

### 7.3 ESLint (`eslint.config.mjs`)

- **Flat config** (ESLint 9): `eslint-plugin-boundaries` v6 uses `boundaries/dependencies` (not legacy `element-types` alone).
- **`no-restricted-imports`**: blocks deep imports under `**/features/*/lib/**`, `**/_internal/**`, `**/api/**`, and relative `../../features/**` style paths.
- **`boundaries/dependencies`**: `app` and `foundation` (`src/components`, `src/lib`, `src/hooks`, `src/types`, `src/config`, `src/proxy.ts`) are separate from `src/features/*/**`; a **feature** may import another **feature** only when it resolves to the **same** captured feature folder (same bounded context). Prefer the barrel `@/features/[name]` for cross-feature calls.
- **Barrel ban (tree-shaking):** still applies to shared code; **`src/features/**` is excluded** from that ban so the feature `index.ts` can act as the public API.

Install (already in `package.json` when integrated):

```bash
pnpm add -D eslint-plugin-boundaries eslint-plugin-import
```

### 7.4 Scripts (`package.json`)

- `pnpm lint` — full ESLint (includes boundary rules).
- `pnpm lint:boundaries` — same ESLint gate (explicit name for architecture CI); keep in sync with `lint`.
- `pnpm verify` — `typecheck` + `lint` + `test`.

### 7.5 GitHub Actions

Workflow `.github/workflows/architecture.yml` runs on PRs touching `src/**` or `*.json` and executes `pnpm verify`.

---

## 8. Checklist per commit

- [ ] Only one module touched (or split agreed)
- [ ] No unrelated `index.ts` edits
- [ ] Cross-feature imports use `@/features/[name]` only
- [ ] No protected files edited without intent
- [ ] Public API unchanged or versioned / documented
- [ ] `pnpm verify` passes locally

---

## 9. Escalation

If respecting boundaries needs a new export from another module:

1. Stop.
2. Name the owning module and the proposed public API.
3. Get explicit approval.
4. Then extend that module’s `index.ts` (or add a deliberate new entry point), without reaching into its internals from outside.
