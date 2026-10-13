import "server-only";

import { writeAuditLog } from "@/lib/audit";
import { logger, type LogContext } from "@/lib/logger";
import type { AuditAction } from "@/lib/audit";
import type { Json } from "@/types/database";
import { createOrg as _createOrg } from "../lib/org";

// ---------------------------------------------------------------------------
// Dependency interfaces — use case depends on these, not on concrete modules.
// This enables testing without vi.mock() — pass stubs directly.
// ---------------------------------------------------------------------------

type OrgCreator = (params: {
  name: string;
  slug: string;
  userId: string;
}) => Promise<{ id: string; slug: string }>;

type AuditWriter = (params: {
  userId: string | null;
  action: AuditAction;
  resource?: string;
  metadata?: Json;
}) => Promise<void>;

export interface CreateOrgDeps {
  createOrg: OrgCreator;
  writeAuditLog: AuditWriter;
  log: (message: string, context?: LogContext) => void;
}

const defaultDeps: CreateOrgDeps = {
  createOrg: _createOrg,
  writeAuditLog,
  log: logger.info.bind(logger),
};

// ---------------------------------------------------------------------------
// Use case
// ---------------------------------------------------------------------------

/**
 * Create an org for a user, write an audit log entry, and emit a log line.
 *
 * Accepts optional `deps` for dependency injection in tests — pass stubs
 * instead of vi.mock() so tests remain framework-independent.
 */
export async function createOrgForUser(
  params: { name: string; slug: string; userId: string },
  deps: CreateOrgDeps = defaultDeps
): Promise<{ id: string; slug: string }> {
  const org = await deps.createOrg(params);

  await deps.writeAuditLog({
    userId: params.userId,
    action: "org.created",
    resource: `organization:${org.id}`,
    metadata: { event: "org_created", slug: org.slug },
  });

  deps.log("org created", { orgId: org.id, userId: params.userId });
  return org;
}

// ---------------------------------------------------------------------------
// Error normalisation (pure — no deps, easy to test)
// ---------------------------------------------------------------------------

export function getCreateOrgErrorResponse(error: unknown): { error: string; status: number } {
  const message = error instanceof Error ? error.message : "Failed to create organization";
  if (message.toLowerCase().includes("unique") || message.toLowerCase().includes("duplicate")) {
    return { error: "That slug is already taken.", status: 409 };
  }
  return { error: message, status: 500 };
}
