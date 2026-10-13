import { NextResponse, type NextRequest } from "next/server";

import { requireUser } from "@/lib/auth";
import { createOrgForUser, getCreateOrgErrorResponse, getUserOrgs } from "@/features/orgs";
import { logger } from "@/lib/logger";
import { limit } from "@/lib/rate-limit";
import { getClientIpFromHeaders } from "@/lib/request-ip";
import { createOrgSchema } from "@/lib/validations";

/** GET /api/orgs — list the current user's organizations. */
export async function GET(): Promise<NextResponse> {
  const user = await requireUser();
  const orgs = await getUserOrgs(user.id);
  return NextResponse.json({ orgs });
}

/** POST /api/orgs — create a new organization. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const user = await requireUser();

  const ip = getClientIpFromHeaders(request.headers);
  const { success } = await limit(`orgs:create:${ip}`, { limit: 10, windowMs: 60_000 });
  if (!success) {
    return NextResponse.json(
      { error: "Too many requests. Try again in a minute." },
      { status: 429 }
    );
  }

  const body = await request.json().catch(() => null);
  const parsed = createOrgSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.issues[0]?.message ?? "Invalid request" },
      { status: 400 }
    );
  }

  try {
    const org = await createOrgForUser({ ...parsed.data, userId: user.id });
    return NextResponse.json({ org }, { status: 201 });
  } catch (error) {
    logger.error("org create failed", error);
    const response = getCreateOrgErrorResponse(error);
    return NextResponse.json({ error: response.error }, { status: response.status });
  }
}
