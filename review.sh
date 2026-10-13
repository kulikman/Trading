#!/bin/bash

# review.sh — запуск полного аудита проекта через Claude Code
# Использование: ./review.sh
# Или с фокусом: ./review.sh security | ./review.sh feature/invoices

FOCUS="${1:-full}"
PROJECT=$(basename "$PWD")

echo "🔍 Starting code review for: $PROJECT"
echo "Focus: $FOCUS"
echo ""

if [ "$FOCUS" = "full" ]; then
  PROMPT="You have access to the full codebase of $PROJECT.

Do a comprehensive pre-emptive audit using the code-reviewer skill.

Scan in this order:
1. Security — auth, RLS, secrets, input validation
2. Correctness — logic bugs, null checks, missing awaits
3. TypeScript — any types, missing return types
4. Performance — N+1 queries, unbounded selects, missing indexes
5. React/Next.js — client/server boundaries, loading/error states
6. Code quality — dead code, duplication, oversized components

Output format:
- 🔴 Critical (must fix)
- 🟡 Warning (should fix)
- 🔵 Suggestion (consider)

Do NOT modify any files. Report only.
Start with src/ directory."

elif [ "$FOCUS" = "security" ]; then
  PROMPT="Security-only audit for $PROJECT.
Check: RLS on all tables, auth before data access, no secrets in client code,
input validation, no service_role on client, getUser() not getSession() on server.
Report only 🔴 Critical and 🟡 Warning findings."

else
  PROMPT="Review the following path for bugs and issues: $FOCUS
Use the code-reviewer skill. Report 🔴 Critical, 🟡 Warning, 🔵 Suggestion."
fi

# Запуск Claude Code с промптом
claude --print "$PROMPT"
