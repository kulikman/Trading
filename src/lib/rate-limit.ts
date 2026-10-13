import "server-only";

import { getServerEnv } from "@/lib/env";

/**
 * Distributed rate limiter.
 *
 * Uses Upstash Redis (sliding window) when UPSTASH_REDIS_REST_URL +
 * UPSTASH_REDIS_REST_TOKEN are set — required for serverless / multi-region.
 * Falls back to an in-memory bucket for local dev (single instance only).
 *
 * The public `limit()` API is intentionally identical in both modes so
 * callers never need to know which backend is active.
 */

export interface RateLimitResult {
  success: boolean;
  remaining: number;
  reset: number;
}

export interface RateLimitOptions {
  /** Max requests per window. */
  limit: number;
  /** Window in milliseconds. */
  windowMs: number;
}

// ---------------------------------------------------------------------------
// Upstash backend
// ---------------------------------------------------------------------------

async function limitWithUpstash(
  key: string,
  { limit, windowMs }: RateLimitOptions
): Promise<RateLimitResult> {
  const { Ratelimit } = await import("@upstash/ratelimit");
  const { Redis } = await import("@upstash/redis");
  const env = getServerEnv();

  const redis = new Redis({
    url: env.UPSTASH_REDIS_REST_URL!,
    token: env.UPSTASH_REDIS_REST_TOKEN!,
  });

  const ratelimit = new Ratelimit({
    redis,
    limiter: Ratelimit.slidingWindow(limit, `${windowMs} ms`),
    prefix: "rl",
  });

  const { success, remaining, reset } = await ratelimit.limit(key);
  return { success, remaining, reset };
}

// ---------------------------------------------------------------------------
// In-memory fallback (dev / single-instance only)
// ---------------------------------------------------------------------------

interface Bucket {
  count: number;
  resetAt: number;
}

const buckets = new Map<string, Bucket>();

function limitInMemory(key: string, { limit, windowMs }: RateLimitOptions): RateLimitResult {
  const now = Date.now();
  const bucket = buckets.get(key);

  if (!bucket || bucket.resetAt < now) {
    buckets.set(key, { count: 1, resetAt: now + windowMs });
    return { success: true, remaining: limit - 1, reset: now + windowMs };
  }

  if (bucket.count >= limit) {
    return { success: false, remaining: 0, reset: bucket.resetAt };
  }

  bucket.count += 1;
  return { success: true, remaining: limit - bucket.count, reset: bucket.resetAt };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Increment-and-check. Returns whether the request is allowed.
 *
 * @example
 *   const { success } = await limit(`login:${ip}`, { limit: 5, windowMs: 60_000 })
 *   if (!success) throw new Error("Too many attempts")
 */
export async function limit(key: string, options: RateLimitOptions): Promise<RateLimitResult> {
  const env = getServerEnv();
  const hasUpstash = env.UPSTASH_REDIS_REST_URL && env.UPSTASH_REDIS_REST_TOKEN;

  if (hasUpstash) {
    return limitWithUpstash(key, options);
  }

  return limitInMemory(key, options);
}
