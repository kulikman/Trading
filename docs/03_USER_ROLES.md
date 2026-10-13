# User Roles

## Overview

This project uses Supabase Auth + a `profiles.role` column for role-based access control.
RLS policies enforce permissions at the database level — never rely on frontend-only checks.

---

## Role: Guest (unauthenticated)

### Description
Any visitor who has not authenticated.

### Permissions
- Can view public landing page, pricing, docs
- Cannot access dashboard or any authenticated routes
- Redirected to `/login` by `src/proxy.ts` on protected routes

---

## Role: User (default)

### Description
Authenticated user on any plan (free, pro, team).

### Permissions
- Can manage own profile via onboarding and account settings (`/settings`)
- Can view and use core product features
- Can upgrade/downgrade subscription (`/settings/billing`)
- Can manage own API keys (`/settings/api-keys`)
- Can view own usage (`/settings/usage`)
- **Cannot** access other users' data
- **Cannot** access admin panel

### Plan-based Limits
See `src/lib/plan-limits.ts` for feature gates per plan.
Gate features with `<PlanGate allowed={limits.feature}>` component.

---

## Role: Admin

### Description
Internal team member with operational access.

### Permissions
- Can view all users
- Can manage content / moderate actions
- Can access admin panel (`/admin`)
- Can view platform-wide analytics
- **Cannot** change system settings or other admins' roles

### How to assign
```sql
UPDATE profiles SET role = 'admin' WHERE id = '[user-id]';
```

---

## Role: Super Admin

### Description
Project owner with full system access.

### Permissions
- All admin permissions
- Can manage admin roles
- Can change system-wide settings
- Can access all data
- Can perform critical operations (data deletion, migrations)

### How to assign
```sql
UPDATE profiles SET role = 'super_admin' WHERE id = '[user-id]';
```

---

## Permission Matrix

| Feature | Guest | User | Admin | Super Admin |
|---|:---:|:---:|:---:|:---:|
| View public pages | ✅ | ✅ | ✅ | ✅ |
| Sign up / Login | ✅ | ✅ | ✅ | ✅ |
| Dashboard | ❌ | ✅ | ✅ | ✅ |
| Own profile | ❌ | ✅ | ✅ | ✅ |
| Core features | ❌ | ✅* | ✅ | ✅ |
| Billing / Stripe | ❌ | ✅ | ✅ | ✅ |
| API keys | ❌ | ✅ | ✅ | ✅ |
| Organizations | ❌ | ✅ | ✅ | ✅ |
| Admin panel | ❌ | ❌ | ✅ | ✅ |
| User management | ❌ | ❌ | ✅ | ✅ |
| System settings | ❌ | ❌ | ❌ | ✅ |

*Subject to plan limits (free/pro/team).

---

## RLS Pattern

Every table must have policies that enforce role boundaries:

```sql
-- Users can only read/write their own rows
CREATE POLICY "users_own_data" ON [table]
  FOR ALL USING (auth.uid() = user_id);

-- Admins can read all rows
CREATE POLICY "admins_read_all" ON [table]
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND role IN ('admin', 'super_admin')
    )
  );
```
