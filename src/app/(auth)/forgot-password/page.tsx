"use client";

import Link from "next/link";
import { useActionState } from "react";

import { SubmitButton } from "@/components/forms/submit-button";
import { ROUTES } from "@/lib/constants";
import { sendPasswordReset, type ForgotPasswordState } from "./actions";

const INITIAL_STATE: ForgotPasswordState = {};

export default function ForgotPasswordPage(): React.ReactElement {
  const [state, formAction] = useActionState(sendPasswordReset, INITIAL_STATE);

  if (state.success) {
    return (
      <div className="flex flex-col gap-4 text-center">
        <div className="bg-primary/10 text-primary mx-auto flex h-12 w-12 items-center justify-center rounded-full text-2xl">
          ✓
        </div>
        <h1 className="text-foreground text-2xl font-semibold tracking-tight">Check your email</h1>
        <p className="text-muted-foreground text-sm">
          If an account exists for that email, we sent a password reset link. Check your inbox.
        </p>
        <Link
          href={ROUTES.login}
          className="text-muted-foreground hover:text-foreground text-sm underline underline-offset-4"
        >
          Back to sign in
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2 text-center">
        <h1 className="text-foreground text-2xl font-semibold tracking-tight">Forgot password?</h1>
        <p className="text-muted-foreground text-sm">
          Enter your email and we&apos;ll send you a reset link.
        </p>
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

        {state.error && (
          <p
            role="alert"
            className="text-destructive bg-destructive/10 rounded-md px-3 py-2 text-sm"
          >
            {state.error}
          </p>
        )}

        <SubmitButton size="lg" className="mt-2" pendingLabel="Sending link…">
          Send reset link
        </SubmitButton>
      </form>

      <Link
        href={ROUTES.login}
        className="text-muted-foreground hover:text-foreground text-center text-sm underline underline-offset-4"
      >
        Back to sign in
      </Link>
    </div>
  );
}
