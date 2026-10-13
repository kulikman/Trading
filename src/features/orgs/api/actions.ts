"use server";

import { createOrgForUser, getCreateOrgErrorResponse } from "./create-org";
import { logger } from "@/lib/logger";
import { requireUser } from "@/lib/auth";
import { createOrgSchema } from "@/lib/validations";

type CreateOrgResult = { ok: true } | { ok: false; error: string };

/**
 * Server Action: create a new organization.
 * Called from OrgCreateForm (client component).
 */
export async function createOrgAction(input: unknown): Promise<CreateOrgResult> {
  const user = await requireUser();

  const parsed = createOrgSchema.safeParse(
    typeof input === "object" && input !== null
      ? {
          name: (input as Record<string, unknown>).name,
          slug: (input as Record<string, unknown>).slug,
        }
      : input
  );
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid input." };
  }

  try {
    await createOrgForUser({ ...parsed.data, userId: user.id });
    return { ok: true };
  } catch (error) {
    logger.error("createOrgAction failed", error);
    const { error: msg } = getCreateOrgErrorResponse(error);
    return { ok: false, error: msg };
  }
}
