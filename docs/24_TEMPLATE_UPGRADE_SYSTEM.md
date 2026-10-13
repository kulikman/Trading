# Template Upgrade System

Updated: 2026-06-20

This is the future layer after policy inventory, validation and PR-only sync.

## Current Decision

Do not migrate existing repositories to Copier or Cruft yet.

The current 25-style portfolio contains established repositories with different
stacks, histories and custom agent files. For these repositories, PR-only file
sync is safer than a full template-management migration.

## Current Upgrade Path

Use this order:

1. Keep `Template-Projects` as the canonical policy source.
2. Generate inventory with `pnpm agent:inventory`.
3. Generate dashboard with `pnpm agent:status`.
4. Validate policy with `pnpm agent:policy-check`.
5. Sync canonical policy bundle through PRs.
6. Add generated-block merge support for live agent files.
7. Only then evaluate template-managed updates.

## When Copier Becomes Useful

Evaluate Copier when new repositories are created directly from a template and
need repeatable future updates.

Useful signals:

- new project creation should preserve template history;
- template answers/variables should be tracked;
- future template updates should be applied with a dedicated update command;
- generated files and manual sections are clearly separated.

## When Cruft Becomes Useful

Evaluate Cruft when a project is Cookiecutter-based or when compatibility with
Cookiecutter-style templates matters.

Useful signals:

- projects already use Cookiecutter metadata;
- template drift needs to be detected explicitly;
- update PRs should show changes from the upstream template.

## Requirements Before Migration

- Generated sections are clearly marked.
- Manual sections are outside generated blocks.
- Target repositories have clean working trees.
- Target repository checks are known and documented.
- Rollback instructions exist.
- Template metadata is committed intentionally.

## Non-Goals For Now

- Do not rewrite existing repositories into a new template structure.
- Do not replace repo-specific `AGENTS.md` or `CLAUDE.md` files wholesale.
- Do not add template update commands that are not implemented.
- Do not describe Copier or Cruft as enabled until metadata exists in target repos.
