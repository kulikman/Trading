# Command: /project:deploy-check

Финальная проверка перед деплоем в production.

## Использование

```
/project:deploy-check
```

## Чеклист

### Code Quality
- [ ] `pnpm tsc --noEmit` — TypeScript без ошибок
- [ ] `pnpm lint` — ESLint чист
- [ ] `pnpm format:check` — Prettier чист
- [ ] `pnpm test` — все тесты зелёные
- [ ] `pnpm build` — сборка успешна

### Security
- [ ] `pnpm audit` — нет HIGH/CRITICAL CVEs
- [ ] Нет захардкоженных секретов (`git grep -r "sk_live\|service_role"`)
- [ ] RLS включён на всех production таблицах
- [ ] `.env.local` не закоммичен

### Environment
- [ ] Все required env vars настроены в Vercel Dashboard
- [ ] `NEXT_PUBLIC_APP_URL` указывает на production домен
- [ ] `NEXT_PUBLIC_APP_URL` — `src/app/robots.ts` отдаёт правильный Sitemap URL
- [ ] `public/llms.txt` — заполнен актуальными данными продукта

### UX
- [ ] 404 страница (`not-found.tsx`) работает
- [ ] Error boundary (`error.tsx`) работает
- [ ] Breadcrumbs на всех вложенных маршрутах
- [ ] Mobile responsiveness проверена

## Output

```
## Deploy Check: [дата]

### ✅ Готово к деплою
### ❌ Блокирует деплой (исправить обязательно)
### ⚠️ Рекомендуется исправить
```
