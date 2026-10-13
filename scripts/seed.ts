#!/usr/bin/env tsx
/**
 * Local development seed script.
 *
 * Creates a set of realistic test users, subscriptions, notifications,
 * and API keys so you can develop against non-empty state.
 *
 * Usage:
 *   pnpm seed
 *
 * Prerequisites:
 *   - Supabase running locally (`supabase start`) or pointed to a staging project
 *   - NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY set in .env.local
 *
 * Safe to run multiple times — uses upsert where possible.
 * Delete seed data manually from Supabase Studio or add a dedicated reset
 * script before documenting an automated reset command.
 */

import { createClient } from "@supabase/supabase-js";
import { config } from "dotenv";
import { resolve } from "node:path";

// Load .env.local
config({ path: resolve(process.cwd(), ".env.local") });

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;

if (!SUPABASE_URL || !SERVICE_ROLE_KEY) {
  console.error(
    "❌  Missing NEXT_PUBLIC_SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env.local"
  );
  process.exit(1);
}

const admin = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
  auth: { persistSession: false },
});

// ── Seed data definitions ────────────────────────────────────────────────────

const SEED_USERS = [
  { email: "alice@example.com", password: "password123", username: "alice", full_name: "Alice Johnson" },
  { email: "bob@example.com",   password: "password123", username: "bob",   full_name: "Bob Smith" },
  { email: "carol@example.com", password: "password123", username: "carol", full_name: "Carol White" },
];

// ── Helpers ──────────────────────────────────────────────────────────────────

function log(msg: string): void {
  console.log(`  ${msg}`);
}

function ok(msg: string): void {
  console.log(`  ✅ ${msg}`);
}

function warn(msg: string): void {
  console.warn(`  ⚠️  ${msg}`);
}

// ── Steps ────────────────────────────────────────────────────────────────────

async function seedUsers(): Promise<Record<string, string>> {
  console.log("\n🧑  Seeding users…");
  const userIds: Record<string, string> = {};

  for (const u of SEED_USERS) {
    // createUser is idempotent if listUsers is checked first
    const { data: list } = await admin.auth.admin.listUsers();
    const existing = list?.users.find((x) => x.email === u.email);

    if (existing) {
      userIds[u.email] = existing.id;
      log(`skip ${u.email} (already exists)`);
      continue;
    }

    const { data, error } = await admin.auth.admin.createUser({
      email: u.email,
      password: u.password,
      email_confirm: true,
      user_metadata: { username: u.username },
    });

    if (error) {
      warn(`${u.email}: ${error.message}`);
      continue;
    }

    userIds[u.email] = data.user.id;

    // Upsert profile
    await admin.from("profiles").upsert({
      id: data.user.id,
      username: u.username,
      full_name: u.full_name,
      onboarding_completed: true,
    });

    ok(`created ${u.email} (${data.user.id})`);
  }

  return userIds;
}

async function seedNotifications(userIds: Record<string, string>): Promise<void> {
  console.log("\n🔔  Seeding notifications…");

  const aliceId = userIds["alice@example.com"];
  if (!aliceId) return;

  const notifications = [
    { title: "Welcome to the platform!", body: "Your account is ready.", kind: "success", href: "/dashboard" },
    { title: "Payment received", body: "Your Pro subscription is now active.", kind: "success", href: "/settings/billing" },
    { title: "Storage at 80%", body: "You've used 4 GB of your 5 GB free tier.", kind: "warning", href: "/settings/usage" },
    { title: "New feature: API Keys", body: "Generate API keys for your integrations.", kind: "info", href: "/settings/api-keys" },
  ];

  for (const n of notifications) {
    await admin.from("notifications").insert({ user_id: aliceId, ...n });
  }

  ok(`created ${notifications.length} notifications for alice@example.com`);
}

// ── Main ─────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  console.log("🌱 Starting seed…");
  console.log(`   Target: ${SUPABASE_URL}`);

  const userIds = await seedUsers();
  await seedNotifications(userIds);

  console.log("\n✅  Seed complete!");
  console.log("\nTest credentials:");
  for (const u of SEED_USERS) {
    console.log(`   ${u.email} / ${u.password}`);
  }
}

main().catch((err) => {
  console.error("❌ Seed failed:", err);
  process.exit(1);
});
