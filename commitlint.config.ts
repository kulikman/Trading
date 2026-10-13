import type { UserConfig } from '@commitlint/types'

/**
 * Commitlint — enforces Conventional Commits on every commit.
 *
 * Types in use:
 *   feat     — new user-facing capability
 *   fix      — bug fix
 *   refactor — internal cleanup, no behavior change
 *   chore    — tooling, deps, CI
 *   docs     — documentation only
 *   test     — adding or fixing tests
 *   perf     — performance improvement
 *   ci       — CI/CD changes
 *   style    — formatting, whitespace (no logic change)
 *   build    — build system changes
 *
 * Breaking changes: add '!' after type — e.g. `feat!: rename API`
 * or add `BREAKING CHANGE:` footer.
 *
 * Scope (optional): the domain being changed — e.g. `feat(auth): ...`
 */
const config: UserConfig = {
  extends: ['@commitlint/config-conventional'],
  ignores: [
    (message) => {
      const header = message.split('\n')[0]?.trim() ?? ''

      // Keep conventional commits validated, but allow simple free-form headers.
      return header.length > 0 && !/^[a-z]+(\([^)]+\))?!?:\s.+$/.test(header)
    },
  ],
  rules: {
    // Max subject line length — keeps git log readable.
    'header-max-length': [2, 'always', 100],

    // Enforce lowercase subject.
    'subject-case': [2, 'always', 'lower-case'],

    // No trailing period in subject.
    'subject-full-stop': [2, 'never', '.'],

    // Allow common scopes for this template. Remove/extend per project.
    'scope-enum': [
      1, // warn (not error) — don't block commits with new scopes
      'always',
      ['auth', 'ui', 'db', 'api', 'ci', 'deps', 'config', 'docs', 'features'],
    ],
  },
}

export default config
