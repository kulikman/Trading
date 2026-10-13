"use client";

import Link from "next/link";
import { useActionState } from "react";

import { SubmitButton } from "@/components/forms/submit-button";
import { ROUTES } from "@/lib/constants";
import { signUp, type SignupState } from "./actions";

const INITIAL_STATE: SignupState = {};

export default function SignupPage(): React.ReactElement {
  const [state, formAction] = useActionState(signUp, INITIAL_STATE);

  if (state.success) {
    return (
      <div className="flex flex-col gap-4 text-center">
        <div className="bg-primary/10 text-primary mx-auto flex h-12 w-12 items-center justify-center rounded-full text-2xl">
          ✓
        </div>
        <h1 className="text-foreground text-2xl font-semibold tracking-tight">Check your email</h1>
        <p className="text-muted-foreground text-sm">
          We sent a confirmation link to your email address. Click it to activate your account.
        </p>
        <p className="text-muted-foreground text-sm">
          Already confirmed?{" "}
          <Link href={ROUTES.login} className="text-foreground underline underline-offset-4">
            Sign in
          </Link>
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2 text-center">
        <h1 className="text-foreground text-2xl font-semibold tracking-tight">Create an account</h1>
        <p className="text-muted-foreground text-sm">Enter your details to get started.</p>
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
          <span className="text-foreground text-sm font-medium">Password</span>
          <input
            type="password"
            name="password"
            required
            autoComplete="new-password"
            minLength={8}
            className="border-input bg-background h-10 rounded-md border px-3 text-sm"
          />
          <span className="text-muted-foreground text-xs">
            Minimum 8 characters, must include a letter and a number.
          </span>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-foreground text-sm font-medium">Confirm password</span>
          <input
            type="password"
            name="confirmPassword"
            required
            autoComplete="new-password"
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

        <SubmitButton size="lg" className="mt-2" pendingLabel="Creating account…">
          Create account
        </SubmitButton>
      </form>

      <p className="text-muted-foreground text-center text-sm">
        Already have an account?{" "}
        <Link href={ROUTES.login} className="text-foreground underline underline-offset-4">
          Sign in
        </Link>
      </p>
    </div>
  );
}
