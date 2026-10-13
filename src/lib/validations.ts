import { z } from "zod";

/**
 * Shared Zod schemas for forms, API request bodies, and query params.
 *
 * Add schemas here when they're used across multiple routes or components.
 * Keep route-specific schemas co-located with the route handler.
 */

/** Email validation — reused across login, signup, invite forms. */
export const emailSchema = z.string().email("Invalid email address");

/** Pagination query params — used by list API routes. */
export const paginationSchema = z.object({
  page: z.coerce.number().int().positive().default(1),
  limit: z.coerce.number().int().min(1).max(100).default(20),
});

/** UUID param — used for dynamic route validation. */
export const uuidParamSchema = z.object({
  id: z.string().uuid("Invalid ID format"),
});

/** Strong password — min 8 chars, requires letter + number. */
export const passwordSchema = z
  .string()
  .min(8, "Password must be at least 8 characters")
  .regex(/[a-zA-Z]/, "Password must contain at least one letter")
  .regex(/[0-9]/, "Password must contain at least one number");

/**
 * Login form. Uses a relaxed `min(8)` rule (NOT `passwordSchema`) on purpose:
 * we don't want to lock out users whose existing password predates a stricter
 * policy. New passwords (signup, reset) are validated against `passwordSchema`.
 */
export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(8, "Password must be at least 8 characters"),
});

/** Signup form. */
export const signupSchema = z
  .object({
    email: emailSchema,
    password: passwordSchema,
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

/** Forgot-password form. */
export const forgotPasswordSchema = z.object({
  email: emailSchema,
});

/** Reset-password form. */
export const resetPasswordSchema = z
  .object({
    password: passwordSchema,
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

/** Org name — 1–100 chars. */
export const orgNameSchema = z
  .string()
  .min(1, "Name must be 1–100 characters.")
  .max(100, "Name must be 1–100 characters.");

/** Org slug — 2–48 lowercase letters, numbers, hyphens. */
export const orgSlugSchema = z
  .string()
  .min(2, "Slug must be 2–48 lowercase letters, numbers, or hyphens.")
  .max(48, "Slug must be 2–48 lowercase letters, numbers, or hyphens.")
  .regex(/^[a-z0-9-]+$/, "Slug must be 2–48 lowercase letters, numbers, or hyphens.");

/** Create-org body — used by the Server Action and the Route Handler. */
export const createOrgSchema = z.object({
  name: orgNameSchema,
  slug: orgSlugSchema,
});
