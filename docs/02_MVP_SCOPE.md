# MVP Scope

## MVP Goal
[Что должен доказать MVP — гипотеза, которую проверяем]

Example: "Prove that [target users] will pay $X/month to [solve pain] without needing [complex feature]."

---

## In Scope

### Must Have (P0 — блокирует запуск)
- [ ] User can sign up and log in (email/OAuth)
- [ ] User completes onboarding flow
- [ ] [Core feature 1]
- [ ] [Core feature 2]
- [ ] User can upgrade to paid plan (Stripe checkout)
- [ ] Basic settings page (profile, billing)

### Should Have (P1 — важно, но не блокирует)
- [ ] Email notifications (transactional)
- [ ] [Secondary feature 1]
- [ ] [Secondary feature 2]
- [ ] Usage metrics page

### Nice to Have (P2 — если останется время)
- [ ] Team / organization support
- [ ] API keys for developer access
- [ ] [Enhancement 1]

---

## Out of Scope (MVP)
- Advanced analytics dashboard
- White-labeling
- Mobile app
- Public API
- [Feature deferred to v2]

---

## MVP User Flow

```text
User visits landing page
  ↓
User signs up (email or Google OAuth)
  ↓
User completes onboarding wizard (3-5 steps)
  ↓
User lands on dashboard
  ↓
User performs core action
  ↓
System processes and saves result
  ↓
User sees value / outcome
  ↓
User hits free tier limit → upgrade prompt
  ↓
User subscribes via Stripe Checkout
  ↓
User has full access
```

---

## MVP Release Criteria

Technical:
- [ ] Core user flow works end-to-end
- [ ] Auth works (sign up, login, logout, password reset)
- [ ] Stripe checkout + webhook functional
- [ ] Database migrations applied
- [ ] RLS policies on all tables
- [ ] No TypeScript errors (`pnpm tsc --noEmit`)
- [ ] No ESLint errors (`pnpm lint`)
- [ ] CI/CD pipeline passing
- [ ] Deployed to production (Vercel)
- [ ] Environment variables configured

Product:
- [ ] At least 5 real users tested the flow
- [ ] No blocking bugs in core flow
- [ ] Error states handled (empty, loading, error)
- [ ] Mobile layout works on iPhone SE and above
