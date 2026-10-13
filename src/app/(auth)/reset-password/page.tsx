"use client";

import { useActionState } from "react";

import { SubmitButton } from "@/components/forms/submit-button";
import { resetPassword, type ResetPasswordState } from "./actions";

const INITIAL_STATE: ResetPasswordState = {};

export default function ResetPasswordPage(): React.ReactElement {
  const [state, formAction] = useActionState(resetPassword, INITIAL_STATE);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2 text-center">
        <h1 className="text-foreground text-2xl font-semibold tracking-tight">Reset password</h1>
        <p className="text-muted-foreground text-sm">Choose a new password for your account.</p>
      </div>

      <form action={formAction} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-foreground text-sm font-medium">New password</span>
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
          <span className="text-foreground text-sm font-medium">Confirm new password</span>
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

        <SubmitButton size="lg" className="mt-2" pendingLabel="Updating password…">
          Update password
        </SubmitButton>
      </form>
    </div>
  );
}
