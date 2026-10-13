import type { Options } from "semantic-release";

/**
 * semantic-release configuration.
 *
 * Runs automatically on every push to `main` via CI.
 * Reads Conventional Commits to determine the next version:
 *   feat  → minor bump (1.x.0)
 *   fix   → patch bump (1.0.x)
 *   feat! → major bump (x.0.0)  (BREAKING CHANGE footer)
 *
 * Setup:
 *   pnpm add -D semantic-release @semantic-release/changelog @semantic-release/git
 *   Add GITHUB_TOKEN to your CI environment (already available in GitHub Actions).
 *
 * @see https://semantic-release.gitbook.io/semantic-release/
 */
const config: Options = {
  branches: [
    "main",
    { name: "beta", prerelease: true },
    { name: "alpha", prerelease: true },
  ],
  plugins: [
    // 1. Analyse commits to determine next version.
    [
      "@semantic-release/commit-analyzer",
      {
        preset: "conventionalcommits",
        releaseRules: [
          { type: "feat", release: "minor" },
          { type: "fix", release: "patch" },
          { type: "perf", release: "patch" },
          { type: "refactor", release: "patch" },
          // docs/chore/style/test → no release by default.
          { type: "docs", release: false },
          { type: "chore", release: false },
          { breaking: true, release: "major" },
        ],
      },
    ],

    // 2. Generate the release notes body (used by GitHub release + CHANGELOG).
    [
      "@semantic-release/release-notes-generator",
      {
        preset: "conventionalcommits",
        presetConfig: {
          types: [
            { type: "feat", section: "✨ Features" },
            { type: "fix", section: "🐛 Bug Fixes" },
            { type: "perf", section: "⚡ Performance" },
            { type: "refactor", section: "♻️ Refactoring" },
            { type: "docs", section: "📝 Docs", hidden: false },
            { type: "chore", hidden: true },
            { type: "style", hidden: true },
            { type: "test", hidden: true },
          ],
        },
      },
    ],

    // 3. Prepend to CHANGELOG.md.
    ["@semantic-release/changelog", { changelogFile: "CHANGELOG.md" }],

    // 4. Create a GitHub Release.
    "@semantic-release/github",

    // 5. Commit the updated CHANGELOG.md and package.json back to main.
    [
      "@semantic-release/git",
      {
        assets: ["CHANGELOG.md", "package.json"],
        message: "chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}",
      },
    ],
  ],
};

export default config;
