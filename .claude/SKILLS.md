# Skills — Команды вызова

Справочник всех скиллов: что делает, когда использовать, примеры вызовов.

Локально реализованы в этом репозитории:

- `/db` → `.claude/skills/supabase-architect/SKILL.md`
- `/ui` → `.claude/skills/premium-animated-ui/SKILL.md`
- `/security` → `.claude/skills/security-hardening/SKILL.md`
- `/ci` → `.claude/skills/github-workflow/SKILL.md`
- `/scope` → `.claude/skills/product-scope/SKILL.md`
- `/launch` → `.claude/skills/launch/SKILL.md`
- `/growth` → `.claude/skills/growth/SKILL.md`
- `/analytics` → `.claude/skills/analytics/SKILL.md`
- `/payments` → `.claude/skills/payments/SKILL.md`
- `/ops` → `.claude/skills/ops/SKILL.md`
- `/review` → `.claude/skills/review/SKILL.md`
- `/architect` → `.claude/skills/architect/SKILL.md`
- `/memory` → `.claude/skills/memory/SKILL.md`
- `/verify` → `.claude/skills/verification/SKILL.md`
- `/debug` → `.claude/skills/systematic-debugging/SKILL.md`
- `/plan` → `.claude/skills/implementation-plan/SKILL.md`
- `/tdd` → `.claude/skills/test-driven-development/SKILL.md`

---

## Принцип работы скиллов

Скилл — это системный промпт для конкретной задачи. Claude переключается в роль специалиста и выдаёт production-ready код, а не объяснения.

**Формат вызова в Cursor:** `/команда [контекст]`
**Формат вызова в Claude.ai:** написать запрос — скилл активируется автоматически по ключевым словам.

---

## `/db` — Supabase Architect

**Скилл:** `supabase-architect`
**Роль:** Старший DBA. Проектирует схемы, пишет RLS, миграции, Edge Functions.
**Выдаёт:** SQL + TypeScript, готовый к копированию.

**Ключевые слова-триггеры:** Supabase, PostgreSQL, RLS, таблица, схема, миграция, Edge Function, хранимые процедуры, auth, storage, realtime

**Примеры вызовов:**

```
/db проектируй схему для SaaS с multi-tenancy: organizations → members → projects → tasks

/db создай таблицу invoices с RLS: пользователь видит только свои, admin видит всё

/db напиши Edge Function отправки email через Resend при создании заказа

/db добавь soft delete ко всем таблицам через deleted_at + trigger

/db создай систему ролей: owner / admin / member с RLS на уровне organization_id

/db настрой realtime subscription для таблицы notifications

/db создай таблицу audit_logs: трекинг всех действий пользователей с user_id, action, metadata
```

---

## `/ui` — Premium Animated UI

**Скилл:** `premium-animated-ui`
**Роль:** World-class UI/UX + frontend engineer. Создаёт кинематографичные интерфейсы.
**Выдаёт:** Next.js / React компоненты с Tailwind, анимациями, темной темой.

**Ключевые слова-триггеры:** лендинг, компонент, страница, дашборд, hero, анимации, UI, design, красиво, премиум

**Примеры вызовов:**

```
/ui hero section для SaaS продукта: заголовок, подзаголовок, CTA кнопка, dashboard preview

/ui dashboard карточки KPI: выручка, активные пользователи, конверсия, churn rate

/ui pricing таблица: 3 тарифа, toggle monthly/annual, highlighted plan, CTA

/ui sidebar навигация с аккордеоном: иконки, active state, collapsed mode

/ui onboarding wizard: 4 шага с прогресс-баром и анимацией между шагами

/ui data table с сортировкой, фильтрами, пагинацией — generic list view

/ui modal создания новой организации с валидацией Zod + react-hook-form
```

## `/security` — Security Hardening

**Скилл:** `security-hardening`
**Роль:** Старший security engineer. Закрывает дыры в auth, API, инфраструктуре.
**Выдаёт:** Middleware код, CSP headers, rate limiting, конфиги защиты.

**Ключевые слова-триггеры:** безопасность, DDoS, brute force, уязвимость, CORS, CSP, rate limiting, JWT, MFA, webhook, secrets

**Примеры вызовов:**

```
/security настрой rate limiting на auth endpoints в Next.js proxy.ts (Supabase auth)

/security добавь CSP headers и security headers в proxy.ts

/security защита webhook от Stripe: верификация подписи

/security аудит: какие данные могут утечь через client components в нашем стеке?

/security настрой Vercel Edge Middleware для блокировки по IP / геолокации

/security MFA через TOTP: схема реализации с Supabase Auth

/security secrets rotation plan: как менять ключи без downtime
```

---

## `/ci` — GitHub Workflow

**Скилл:** `github-workflow`
**Роль:** DevOps инженер. Строит CI/CD пайплайны, автоматизацию, branch protection.
**Выдаёт:** GitHub Actions YAML, скрипты, конфигурации.

**Ключевые слова-триггеры:** CI/CD, GitHub Actions, деплой, pipeline, PR checks, branch protection, автоматизация

**Примеры вызовов:**

```
/ci создай базовый workflow: lint + typecheck + build при каждом push и PR

/ci настрой автодеплой на Vercel при merge в main, preview при PR

/ci добавь Supabase миграции в pipeline: auto-migrate staging при PR, production при merge

/ci настрой branch protection: require PR review, require CI pass, no direct push to main

/ci создай workflow release: bump version, changelog, GitHub Release при тэге v*

/ci добавь проверку secrets leaks (gitleaks) в pre-commit hook
```

---

## `/review` — Code Reviewer

**Скилл:** `code-reviewer`
**Роль:** Старший инженер. Ищет реальные проблемы — баги, уязвимости, N+1, missing RLS.
**Выдаёт:** Структурированный отчёт: Critical / Warning / Suggestion.

**Ключевые слова-триггеры:** review, проверь код, найди баги, аудит, PR review, что не так

**Примеры вызовов:**

```
/review src/app/api/invoices/route.ts

/review этот компонент — проверь на N+1, missing await, типы

/review вся папка src/features/billing/ — security audit

/review миграция 0008_add_projects.sql — RLS и индексы

/review webhook handler — CORS, auth, error handling, idempotency

# Прямо в тексте:
"Проверь этот код на безопасность: [вставить код]"
"Найди все проблемы в этом компоненте: [вставить]"
```

**Что проверяет автоматически:**
- N+1 запросы
- service_role в клиенте
- trust client user_id (использование user_id из тела запроса вместо auth.uid())
- missing await
- missing RLS
- getSession() на сервере вместо getUser()
- secrets в client components

---

## `/verify` — Verification

**Скилл:** `verification`
**Роль:** Строгий verification engineer. Не разрешает заявлять "готово" без свежих доказательств.
**Выдаёт:** Список проверенных claim'ов, команды, результаты и остаточные риски.

**Ключевые слова-триггеры:** готово, проверь, passing, fixed, commit, push, ship, release, verify

**Примеры вызовов:**

```
/verify перед коммитом: проверь diff, команды и антигаллюцинации

/verify работа готова? докажи через package.json и pnpm verify

/verify проверь, что не придуманы env vars, routes и команды
```

---

## `/debug` — Systematic Debugging

**Скилл:** `systematic-debugging`
**Роль:** Repro-first debugging engineer. Сначала воспроизводит и ищет root cause, потом чинит.
**Выдаёт:** Expected vs actual, reproduction, root cause, минимальный фикс, regression test, checks.

**Ключевые слова-триггеры:** баг, ошибка, падает, failing test, runtime error, regression, broken, debug

**Примеры вызовов:**

```
/debug pnpm verify падает на TypeScript ошибке

/debug кнопка отправляет форму, но API возвращает 500

/debug тест flaky: найди root cause, не патчь симптом
```

---

## `/plan` — Implementation Plan

**Скилл:** `implementation-plan`
**Роль:** Senior engineer для MVP-first планирования. Разбивает сложную работу на проверяемые шаги.
**Выдаёт:** Goal, source of truth, tasks, files likely to change, verification, risks.

**Ключевые слова-триггеры:** план, эпик, roadmap, scope, refactor, много файлов, архитектурный шаг

**Примеры вызовов:**

```
/plan добавить billing MVP без изменения auth

/plan разбей rollback engine на маленькие проверяемые задачи

/plan рефакторинг CLI: файлы, тесты, риски
```

---

## `/tdd` — Test-Driven Development

**Скилл:** `test-driven-development`
**Роль:** Behavior-first engineer. Сначала failing test, потом минимальный код, потом refactor.
**Выдаёт:** Red/green/refactor отчёт и команды проверки.

**Ключевые слова-триггеры:** тест, regression, bugfix, behavior change, refactor, TDD, failing test

**Примеры вызовов:**

```
/tdd добавить проверку: next16 запрещает middleware.ts

/tdd воспроизвести баг парсера YAML через failing test

/tdd покрыть CLI команду snapshot regression test
```

---

## Быстрая шпаргалка

```
Задача                              Команда
─────────────────────────────────────────────────────
Новая таблица / схема / RLS         /db [описание]
UI компонент / страница             /ui [описание]
Безопасность / auth / headers       /security [угроза]
CI/CD / GitHub Actions              /ci [что автоматизировать]
Проверка кода                       /review [файл или код]
Доказать готовность                 /verify [claim]
Дебаг с root cause                  /debug [симптом]
План сложной задачи                 /plan [цель]
TDD для behavior change             /tdd [поведение]
Сохранить контекст сессии           /memory update
Восстановить контекст               /memory show
```

---

## Когда скилл НЕ нужен

- Общий вопрос по коду → просто спроси
- Дебаг конкретного бага → `/debug` + симптом
- Рефакторинг одного файла → `/review` + правки
- Архитектурное решение → `/architect`, `/plan` или описание задачи

Скилл нужен когда нужен **артефакт** (код, файл, конфиг), а не объяснение.
