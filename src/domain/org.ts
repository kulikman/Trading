/**
 * Org domain — pure TypeScript interfaces.
 *
 * RULE: This file must have zero external dependencies.
 * No imports from @/lib, @/features, @/app, or any npm package.
 * Only TypeScript built-ins are allowed.
 *
 * Everything that depends on Supabase / Next.js / external services lives in
 * the infrastructure layer (src/features/orgs/lib/, src/lib/).
 */

/** @public */
export type OrgRole = "owner" | "admin" | "member";

/** @public */
export interface OrgMembership {
  orgId: string;
  orgName: string;
  orgSlug: string;
  role: OrgRole;
}

/** Parameters for creating a new organization. */
export interface CreateOrgParams {
  name: string;
  slug: string;
  userId: string;
}

/**
 * Repository interface for org persistence.
 *
 * NOTE: The current infrastructure functions in `src/features/orgs/lib/org.ts`
 * read userId from the auth session cookie internally and do NOT implement this
 * interface directly. This interface describes the contract a proper DI-based
 * repository would expose — wire it up when refactoring lib/org.ts into a class.
 *
 * @public
 */
export interface OrgRepository {
  create(params: CreateOrgParams): Promise<{ id: string; slug: string }>;
  getUserOrgs(userId: string): Promise<OrgMembership[]>;
  getMembership(userId: string, slug: string): Promise<OrgMembership | null>;
}
