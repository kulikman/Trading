# Rule: Clean Architecture + SOLID

> Applied by: coder, architect agents before writing any feature logic.
> The canonical example is `src/features/orgs/` — read it before implementing a new feature.

---

## Layer Map

Dependency direction: **app → features → lib → domain** (never the reverse).

```
src/app/           [Frameworks & Drivers]
  └─ Server Actions, Route Handlers, React Components
     │ thin — validate input, compose deps, call use case, revalidate

src/features/[name]/api/  [Use Cases / Application Layer]
  └─ Pure business logic orchestration
     │ accepts dependencies as function parameters (DI)
     │ testable without vi.mock() — pass stubs directly

src/features/[name]/lib/  [Infrastructure / Interface Adapters]
  └─ Supabase queries, external API calls, file system
     │ implements domain interfaces

src/domain/        [Domain / Entities]
  └─ Pure TypeScript interfaces and entity types
     │ ZERO external dependencies (no @/lib, no npm packages)
```

---

## SOLID in This Codebase

### S — Single Responsibility
- One file = one reason to change
- `validate.ts` validates, `repository.ts` queries, `use-case.ts` orchestrates
- Server Actions are thin: auth check → parse input → call use case → revalidate

### O — Open/Closed
- Extend via new objects, not if/else chains
- Adding a new plan = new entry in `plan-limits.ts`, zero code changes elsewhere
- Adding a new email template = new function in `templates.ts`

### L — Liskov Substitution
- Interfaces must be fully substitutable
- Test stubs that implement the same interface as production code are always valid
- Never violate the contract by returning `undefined` when `Promise<T>` is declared

### I — Interface Segregation
- Keep interfaces narrow — only what the use case actually needs
- `CreateOrgDeps` defines 3 functions, not a full `OrgService` with 10 methods
- Route Handlers and Server Actions don't share a single interface

### D — Dependency Inversion
- Use cases depend on interfaces, not concrete Supabase/Stripe classes
- Server Actions instantiate concrete implementations and inject them into use cases
- Enables testing without mocking modules — pass stubs as function parameters

---

## Patterns to Follow

### Use Case with Dependency Injection

```ts
// src/features/[name]/api/use-case.ts
import "server-only";

import type { Dependency } from "@/domain/[name]";

export interface UseCaseDeps {
  repo: Dependency;
  log: (msg: string) => void;
}

const defaultDeps: UseCaseDeps = {
  repo: new SupabaseRepository(),
  log: logger.info.bind(logger),
};

export async function myUseCase(
  params: { ... },
  deps: UseCaseDeps = defaultDeps,   // ← default = production deps
): Promise<Result> {
  const result = await deps.repo.doSomething(params);
  deps.log("done", { id: result.id });
  return result;
}
```

### Test Without vi.mock()

```ts
// src/features/[name]/api/use-case.test.ts
import { vi, describe, it, expect, beforeEach } from "vitest";
import { myUseCase, type UseCaseDeps } from "./use-case";

function makeStubs(): UseCaseDeps {
  return {
    repo: { doSomething: vi.fn().mockResolvedValue({ id: "x" }) },
    log: vi.fn(),
  };
}

describe("myUseCase()", () => {
  let deps: UseCaseDeps;
  beforeEach(() => { deps = makeStubs(); });

  it("calls repo and logs", async () => {
    await myUseCase({ ... }, deps);
    expect(deps.repo.doSomething).toHaveBeenCalledWith(...);
    expect(deps.log).toHaveBeenCalledWith("done", { id: "x" });
  });
});
```

### Thin Server Action

```ts
// src/features/[name]/api/actions.ts
"use server";

export async function createThingAction(input: unknown): Promise<Result> {
  // 1. Auth
  const user = await requireUser();
  // 2. Validate
  const data = schema.parse(input);
  // 3. Call use case (deps injected automatically via defaults)
  const result = await myUseCase({ ...data, userId: user.id });
  // 4. Invalidate cache
  revalidateTag(`things:${user.id}`);
  return result;
}
```

### Domain Interface

```ts
// src/domain/[name].ts
// ZERO external imports — only TypeScript built-ins.

export interface MyEntity {
  id: string;
  name: string;
}

export interface MyRepository {
  findById(id: string): Promise<MyEntity | null>;
  create(data: Omit<MyEntity, "id">): Promise<MyEntity>;
}
```

---

## What NOT to Do

```ts
// ❌ Use case with hardcoded deps (can't test without vi.mock)
export async function createThing(params) {
  const supabase = await createServerClient()      // hardcoded
  const { data, error } = await supabase.from("things").insert(params)
  await writeAuditLog({ ... })                     // hardcoded
  logger.info("thing created")                     // hardcoded
}

// ❌ Fat Server Action with business logic
export async function createThingAction(input: FormData) {
  const supabase = await createServerClient()
  const name = input.get("name") as string
  if (!name || name.length > 100) return { error: "..." }   // validation here
  const slug = name.toLowerCase().replace(/ /g, "-")        // business rule here
  await supabase.from("things").insert({ name, slug })       // DB query here
  await sendEmail({ to: user.email, ... })                   // email here
}

// ❌ Importing concrete Supabase class inside a use case
import { createClient } from "@/lib/supabase/server"   // infrastructure leak into use case

// ❌ Domain importing from lib or features
// src/domain/org.ts
import { createClient } from "@/lib/supabase/server"   // NEVER
```

---

## When to Apply

| Situation | Pattern |
|---|---|
| New feature with DB + email + audit | Use case with `Deps` interface |
| Simple read-only query (no side effects) | Direct Supabase call in Server Component is OK |
| Auth-only validation | Keep in Server Action, no use case needed |
| Multiple callers of same logic | Extract to use case with DI |
| Test is hard to write without vi.mock | That's the signal — refactor to DI |

---

## File Naming Convention

```
src/features/[name]/
  api/
    actions.ts          ← Server Actions (thin entry points from React)
    [verb]-[noun].ts    ← Use cases: create-org.ts, send-invite.ts
    [verb]-[noun].test.ts
  lib/
    [noun].ts           ← Repository / queries (Supabase-specific)
    [noun].test.ts
  components/
    [noun]-[form|card|list].tsx
  index.ts              ← Public API re-exports only

src/domain/
  [noun].ts             ← Entity types + repository interfaces
  index.ts              ← Re-exports
```
