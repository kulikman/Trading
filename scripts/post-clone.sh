#!/usr/bin/env bash
# post-clone.sh — Run after forking template-starter to personalize the project.
#
# Usage:
#   bash scripts/post-clone.sh "My Product" "my-product" "https://myproduct.com"
#
# Arguments:
#   $1 — Display name (e.g. "NeoSIM", "2Sky CRM")
#   $2 — Package name / slug (e.g. "neosim", "2sky-crm")
#   $3 — Production URL (e.g. "https://neosim.app")

set -euo pipefail

DISPLAY_NAME="${1:-}"
SLUG="${2:-}"
PROD_URL="${3:-}"

if [[ -z "$DISPLAY_NAME" || -z "$SLUG" || -z "$PROD_URL" ]]; then
  echo "Usage: bash scripts/post-clone.sh \"Display Name\" \"slug\" \"https://url.com\"" >&2
  exit 1
fi

# ── Footgun guard ────────────────────────────────────────────────────────────
# This script ends with `rm -rf .git && git init`. Running it in an existing
# project nukes history. Refuse unless the repo looks like a fresh template
# checkout (≤5 commits) or the user explicitly opts in via --force-reinit.
FORCE_REINIT=false
for arg in "$@"; do
  [[ "$arg" == "--force-reinit" ]] && FORCE_REINIT=true
done

if [[ -d .git && "$FORCE_REINIT" != "true" ]]; then
  COMMITS=$(git log --oneline 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$COMMITS" -gt 5 ]]; then
    echo "✋ Refusing to reinit git: this repo has $COMMITS commits." >&2
    echo "   This script is meant for fresh template checkouts." >&2
    echo "   If you really mean it, re-run with --force-reinit." >&2
    exit 1
  fi
fi

# Refuse if package.json doesn't look like our template (already renamed).
if [[ -f package.json ]] && ! grep -q '"name": "template-starter"' package.json; then
  echo "✋ package.json is not template-starter — looks already personalized." >&2
  echo "   Re-run with --force-reinit if you really want to overwrite." >&2
  [[ "$FORCE_REINIT" != "true" ]] && exit 1
fi

echo "→ Personalizing project: $DISPLAY_NAME ($SLUG)"

# ── package.json ─────────────────────────────────────────────────────────────
if [[ -f package.json ]]; then
  sed -i.bak "s/\"name\": \"template-starter\"/\"name\": \"$SLUG\"/" package.json
  rm -f package.json.bak
  echo "  ✓ package.json name → $SLUG"
fi

# ── .env.example ─────────────────────────────────────────────────────────────
# Leave NEXT_PUBLIC_APP_URL pointed at localhost:3000 — `.env.example` is the
# *local-dev* template; the production URL is set via `vercel env`, not here.
if [[ -f .env.example ]]; then
  sed -i.bak "s|NEXT_PUBLIC_APP_NAME=Template Starter|NEXT_PUBLIC_APP_NAME=$DISPLAY_NAME|" .env.example
  rm -f .env.example.bak
  echo "  ✓ .env.example APP_NAME → $DISPLAY_NAME"
fi

# ── src/config/site.ts ───────────────────────────────────────────────────────
# `siteConfig` is the single source of truth — `layout.tsx` reads from it,
# so we only need to touch site.ts (no separate layout sed).
if [[ -f src/config/site.ts ]]; then
  sed -i.bak "s|name: \"Template Starter\"|name: \"$DISPLAY_NAME\"|" src/config/site.ts
  sed -i.bak "s|Universal Next.js + Supabase starter — fork and rename for your product.|$DISPLAY_NAME — powered by Next.js + Supabase.|" src/config/site.ts
  sed -i.bak "s|url: \"http://localhost:3000\"|url: \"$PROD_URL\"|" src/config/site.ts
  sed -i.bak "s|https://github.com/kulikman/Template-Projects|https://github.com/kulikman/$SLUG|" src/config/site.ts
  sed -i.bak "s|https://github.com/kulikman/template-starter|https://github.com/kulikman/$SLUG|" src/config/site.ts
  rm -f src/config/site.ts.bak
  echo "  ✓ site.ts → $DISPLAY_NAME ($PROD_URL)"
fi

# robots.txt is generated dynamically by `src/app/robots.ts` from
# NEXT_PUBLIC_APP_URL — no static `public/robots.txt` to patch.

# ── public/llms.txt ──────────────────────────────────────────────────────────
if [[ -f public/llms.txt ]]; then
  sed -i.bak "s|# ProjectName|# $DISPLAY_NAME|" public/llms.txt
  sed -i.bak "s|https://example.com|$PROD_URL|" public/llms.txt
  rm -f public/llms.txt.bak
  echo "  ✓ llms.txt → $DISPLAY_NAME"
fi

# ── src/lib/constants.ts ─────────────────────────────────────────────────────
if [[ -f src/lib/constants.ts ]]; then
  sed -i.bak "s|\"Template Starter\"|\"$DISPLAY_NAME\"|" src/lib/constants.ts
  rm -f src/lib/constants.ts.bak
  echo "  ✓ constants.ts APP_NAME fallback → $DISPLAY_NAME"
fi

# ── Clean up git for fresh start ─────────────────────────────────────────────
if [[ -d .git ]]; then
  rm -rf .git
  git init
  git add .
  git commit -m "chore: initialize $DISPLAY_NAME from template-starter"
  echo "  ✓ Fresh git history"
fi

echo ""
echo "✅ Project personalized: $DISPLAY_NAME"
echo ""
echo "Next steps:"
echo "  1. cp .env.example .env.local && fill in Supabase keys"
echo "  2. pnpm install"
echo "  3. pnpm dev"
echo "  4. Update public/llms.txt with product description"
echo "  5. Confirm NEXT_PUBLIC_APP_URL; src/app/robots.ts uses it for Sitemap"
echo ""
