#!/usr/bin/env bash
# init-project-structure.sh
# Scaffolds the full project structure for a new project from this template.
# Usage: bash scripts/init-project-structure.sh [--force] <target-dir>
# From pnpm: pnpm init:structure -- [--force] <target-dir>

set -euo pipefail

FORCE=false
TARGET_DIR=""

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=true ;;
    *) TARGET_DIR="$arg" ;;
  esac
done

if [[ -z "$TARGET_DIR" ]]; then
  echo "Usage: $0 [--force] <target-dir>" >&2
  exit 1
fi

TARGET_DIR="$(realpath "$TARGET_DIR")"

if [[ -d "$TARGET_DIR" && "$(ls -A "$TARGET_DIR" 2>/dev/null)" != "" && "$FORCE" != "true" ]]; then
  echo "Error: '$TARGET_DIR' is not empty. Use --force to scaffold anyway." >&2
  exit 1
fi

mkdir -p "$TARGET_DIR"
echo "→ Scaffolding project structure in: $TARGET_DIR"

# ── src/ ──────────────────────────────────────────────────────────────────────
SRC_DIRS=(
  "src/app/(auth)"
  "src/app/(dashboard)"
  "src/app/api"
  "src/components/ui"
  "src/components/forms"
  "src/components/layout"
  "src/lib/supabase"
  "src/hooks"
  "src/types"
  "src/config"
)

for dir in "${SRC_DIRS[@]}"; do
  mkdir -p "$TARGET_DIR/$dir"
done

# ── .claude/ — AI agent memory and skills ────────────────────────────────────
CLAUDE_DIRS=(
  ".claude/memory"
  ".claude/skills/design/data"
  ".claude/skills/architect"
  ".claude/skills/memory"
  ".claude/skills/review"
)

for dir in "${CLAUDE_DIRS[@]}"; do
  mkdir -p "$TARGET_DIR/$dir"
done

# ── .cursor/ — Cursor rules ───────────────────────────────────────────────────
mkdir -p "$TARGET_DIR/.cursor/rules"

# ── .github/ — CI/CD ─────────────────────────────────────────────────────────
mkdir -p "$TARGET_DIR/.github/workflows"

# ── .vscode/ ─────────────────────────────────────────────────────────────────
mkdir -p "$TARGET_DIR/.vscode"

# ── public/ ───────────────────────────────────────────────────────────────────
mkdir -p "$TARGET_DIR/public"

# ── scripts/ ──────────────────────────────────────────────────────────────────
mkdir -p "$TARGET_DIR/scripts"

# ── Copy template files if TEMPLATE_STARTER_ROOT is set ──────────────────────
TEMPLATE_ROOT="${TEMPLATE_STARTER_ROOT:-}"

if [[ -n "$TEMPLATE_ROOT" && -d "$TEMPLATE_ROOT" ]]; then
  echo "→ Copying files from template: $TEMPLATE_ROOT"

  FILES_TO_COPY=(
    "CLAUDE.md"
    "AGENTS.md"
    ".env.example"
    ".gitignore"
    ".prettierrc"
    ".prettierignore"
    "next.config.ts"
    "tsconfig.json"
    "eslint.config.mjs"
    "postcss.config.mjs"
    "components.json"
    "package.json"
    "pnpm-workspace.yaml"
    "vitest.config.ts"
  )

  for f in "${FILES_TO_COPY[@]}"; do
    if [[ -f "$TEMPLATE_ROOT/$f" ]]; then
      cp "$TEMPLATE_ROOT/$f" "$TARGET_DIR/$f"
      echo "  copied: $f"
    fi
  done

  # Copy .claude/ directory tree
  if [[ -d "$TEMPLATE_ROOT/.claude" ]]; then
    cp -r "$TEMPLATE_ROOT/.claude/." "$TARGET_DIR/.claude/"
    echo "  copied: .claude/"
  fi

  # Copy .cursor/ directory tree
  if [[ -d "$TEMPLATE_ROOT/.cursor" ]]; then
    cp -r "$TEMPLATE_ROOT/.cursor/." "$TARGET_DIR/.cursor/"
    echo "  copied: .cursor/"
  fi

  # Copy .github/ directory tree
  if [[ -d "$TEMPLATE_ROOT/.github" ]]; then
    cp -r "$TEMPLATE_ROOT/.github/." "$TARGET_DIR/.github/"
    echo "  copied: .github/"
  fi

  # Copy .vscode/
  if [[ -d "$TEMPLATE_ROOT/.vscode" ]]; then
    cp -r "$TEMPLATE_ROOT/.vscode/." "$TARGET_DIR/.vscode/"
    echo "  copied: .vscode/"
  fi

  # Copy public/ (llms.txt, favicons, etc.)
  if [[ -d "$TEMPLATE_ROOT/public" ]]; then
    cp -r "$TEMPLATE_ROOT/public/." "$TARGET_DIR/public/"
    echo "  copied: public/"
  fi

  # Copy audit/ (rules + prompt)
  if [[ -d "$TEMPLATE_ROOT/audit" ]]; then
    cp -r "$TEMPLATE_ROOT/audit/." "$TARGET_DIR/audit/"
    echo "  copied: audit/"
  fi

else
  echo "→ No TEMPLATE_STARTER_ROOT set — creating placeholder files only"

  # Create minimal placeholder files
  touch "$TARGET_DIR/CLAUDE.md"
  touch "$TARGET_DIR/AGENTS.md"
  touch "$TARGET_DIR/.env.example"
  touch "$TARGET_DIR/.gitignore"

  # Create minimal memory files
  cat > "$TARGET_DIR/.claude/memory/project-state.md" << 'EOF'
# Project State — Session Memory
> Update this file at the end of each Claude Code session.

## Current Session
**Last Updated:** [date]
**Feature:** [current feature]
**Status:** not started

## Next Steps
1. Set up environment (.env.local)
2. Configure Supabase project
3. Run pnpm install
EOF

  touch "$TARGET_DIR/.claude/memory/decisions.md"
  touch "$TARGET_DIR/.claude/memory/patterns.md"
  touch "$TARGET_DIR/.claude/instincts.md"
fi

# ── Create placeholder src files ─────────────────────────────────────────────
touch "$TARGET_DIR/src/app/layout.tsx"
touch "$TARGET_DIR/src/app/page.tsx"
touch "$TARGET_DIR/src/lib/utils.ts"
touch "$TARGET_DIR/src/lib/constants.ts"
touch "$TARGET_DIR/src/lib/validations.ts"
touch "$TARGET_DIR/src/lib/supabase/client.ts"
touch "$TARGET_DIR/src/lib/supabase/server.ts"
touch "$TARGET_DIR/src/lib/supabase/admin.ts"
touch "$TARGET_DIR/src/types/index.ts"
touch "$TARGET_DIR/src/config/site.ts"

echo ""
echo "✅ Project structure created at: $TARGET_DIR"
echo ""
echo "Next steps:"
echo "  1. cd $TARGET_DIR"
echo "  2. pnpm install"
echo "  3. cp .env.example .env.local && fill in values"
echo "  4. pnpm dev"
echo ""
echo "Claude Code will read CLAUDE.md and .claude/memory/project-state.md automatically."
