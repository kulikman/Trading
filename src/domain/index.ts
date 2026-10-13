/**
 * Domain layer — pure TypeScript interfaces and entity types.
 *
 * RULE: Files in src/domain/ must have zero external dependencies.
 * No imports from @/lib, @/features, @/app, or npm packages.
 *
 * Dependency direction: app → features → lib → domain (never the reverse).
 *
 * @public
 */
export type { OrgRole, OrgMembership, CreateOrgParams, OrgRepository } from "./org";
