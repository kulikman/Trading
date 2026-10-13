# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2026-07-29

### Added
- feat(api): rate limiting for orgs and stripe routes; add playwright e2e specs
- feat(arch): add clean architecture domain layer and dependency injection
- feat(routing): add route contract breadcrumbs
- feat(config): add pr propagation engine
- feat(sfo): validate target policy profiles
- feat(config): add safe renovate baseline
- feat(docs): add agent policy status dashboard
- feat(sfo): add agent policy validation checks
- feat(sfo): add stack and domain policy packs
- feat(ci): add manual agent policy sync workflow
- feat(sfo): add local repo policy inventory

### Fixed
- fix(deps): close 21 high-severity Dependabot alerts
- fix(arch): fix 5 issues found in clean architecture review
- fix(domain): fix 3 hallucinations found in audit
- fix(config): remove unused route type
- fix(deps): clear production audit failures
- fix(sfo): sync complete canonical policy bundle
- fix(ci): replace agent policy sync action dry run
- fix(ci): allow agent policy sync dry run without pat

### Changed
- docs(status): mark rules sync complete across all 20 ecosystem repos
- chore(ci): disable ai attribution in commits and settings
- chore(deps): bump pnpm to 10.32.1, fix audit registry error
- chore(ci): add bash validation layer to commit-msg hook
- docs(template): update architecture, status, and decisions docs
- chore(release): 0.18.2 [skip ci]
- chore(release): 0.18.1 [skip ci]
- chore(release): 0.18.0 [skip ci]
- chore(release): 0.17.0 [skip ci]
- docs(policy): refresh repository sync status
- chore(release): 0.16.1 [skip ci]
- chore(release): 0.16.0 [skip ci]
- chore(release): 0.15.0 [skip ci]
- chore(release): 0.14.1 [skip ci]
- docs: mark policy rollout worktrees clean

