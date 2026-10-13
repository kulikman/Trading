# Rule: Architecture

> Читается агентами architect и coder перед проектированием features.

## Структура проекта

```
src/
├── app/                  # Next.js App Router
│   ├── (auth)/           # Auth routes
│   ├── (dashboard)/      # Protected routes
│   ├── api/              # Route Handlers
│   ├── error.tsx         # Global error boundary
│   ├── not-found.tsx     # 404
│   ├── loading.tsx       # Global loading skeleton
│   └── sitemap.ts        # Dynamic sitemap
├── components/
│   ├── ui/               # shadcn primitives
│   ├── forms/            # Form components
│   └── layout/           # Header, Breadcrumbs, etc.
├── lib/
│   ├── supabase/         # client, server, admin, middleware
│   ├── env.ts            # Zod env validation
│   ├── utils.ts          # cn() и утилиты
│   ├── constants.ts      # ROUTES и константы
│   └── validations.ts    # Общие Zod schemas
├── hooks/
├── types/
├── config/site.ts
└── proxy.ts              # Session refresh + security headers
```

## Source Of Truth

- Сначала читай реальные файлы и существующие контракты, потом предлагай изменения.
- Не выдумывай сервисы, модули, API contracts, database columns или feature boundaries.
- Если нужного контракта нет, сначала зафиксируй этот факт, а не маскируй его предположением.
- Не меняй роль файла без явной причины: `proxy.ts`, `env.ts`, `database.ts`, migrations и webhook paths считаются специальными.

## URL Hierarchy

- URL отражают иерархию: `/docs/getting-started` → `/docs` тоже валидная страница.
- Каждый layout во вложенном route включает `<Breadcrumbs />`.
- Динамические сегменты (`[slug]`) → передавай `resolveLabel` prop.
- Route groups `(auth)`, `(dashboard)` невидимы в URL, стрипаются в breadcrumbs.
- Нельзя создавать `/a/b/c` без `/a/b` и `/a` как валидных страниц.

## Компоненты

- Используется в 2+ местах → `components/[feature]/`
- Специфичен для одной страницы и < 50 строк → оставляй inline
- Файл > 150 строк → сплити
- Логика + presentation перемешаны → разделяй

## Data Flow

- Server Components фетчат данные напрямую через `async/await`
- Client Components получают данные через props или SWR/React Query для real-time
- Server Actions для mutations (с CSRF защитой через `verifyCsrfOrigin`)
- Edge Functions для: webhooks, 3rd-party API с секретами, файлы

## Caching (Next 16)

- Кэширование opt-in через `"use cache"` directive
- Не полагайся на implicit memoization — это убрали в Next 16
- Будь явным в том, что кэшируется

## Metadata

- Root layout: `title.template` из `siteConfig`
- Динамические страницы → `generateMetadata()`
- Всегда указывай `width` и `height` для OG images (default: 1200×630)
