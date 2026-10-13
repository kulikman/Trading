"use client";

import Link from "next/link";
import { useActionState } from "react";

import { SubmitButton } from "@/components/forms/submit-button";
import { ROUTES } from "@/lib/constants";
import { signInWithPassword, type LoginState } from "./actions";

const INITIAL_STATE: LoginState = {};

/**
 * Skeleton login. Demonstrates the canonical React 19 + Next 16 pattern:
 *   - `useActionState` connects a Server Action to a Client form
 *   - `<SubmitButton>` reads `useFormStatus()` for pending state
 *   - Errors are returned (not thrown) so the UI re-renders cleanly
 */
export default function LoginPage(): React.ReactElement {
  const [state, formAction] = useActionState(signInWithPassword, INITIAL_STATE);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2 text-center">
        <h1 className="text-foreground text-2xl font-semibold tracking-tight">Welcome back</h1>
        <p className="text-muted-foreground text-sm">Sign in to continue.</p>
      </div>

      <form action={formAction} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-foreground text-sm font-medium">Email</span>
          <input
            type="email"
            name="email"
            required
            autoComplete="email"
            className="border-input bg-background h-10 rounded-md border px-3 text-sm"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <span className="text-foreground text-sm font-medium">Password</span>
            <Link
              href={ROUTES.forgotPassword}
              className="text-muted-foreground hover:text-foreground text-xs underline underline-offset-4"
            >
              Forgot password?
            </Link>
          </div>
          <input
            type="password"
            name="password"
            required
            autoComplete="current-password"
            minLength={8}
            className="border-input bg-background h-10 rounded-md border px-3 text-sm"
          />
        </label>

        {state.error && (
          <p
            role="alert"
            className="text-destructive bg-destructive/10 rounded-md px-3 py-2 text-sm"
          >
            {state.error}
          </p>
        )}

        <SubmitButton size="lg" className="mt-2" pendingLabel="Signing in…">
          Sign in
        </SubmitButton>
      </form>

      <p className="text-muted-foreground text-center text-sm">
        Don&apos;t have an account?{" "}
        <Link href={ROUTES.signup} className="text-foreground underline underline-offset-4">
          Sign up
        </Link>
      </p>
    </div>
  );
}
