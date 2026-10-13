"use client";

import { useFormStatus } from "react-dom";

import { Button } from "@/components/ui/button";
import type { ComponentProps } from "react";

type ButtonProps = ComponentProps<typeof Button>;

interface SubmitButtonProps extends ButtonProps {
  pendingLabel?: string;
}

/**
 * Submit button that auto-disables and shows a pending label while the
 * surrounding `<form action={serverAction}>` is in flight.
 *
 * Use this everywhere a Server Action mutates data — visual pending state
 * is the cheapest UX win in React 19's new form model.
 */
export function SubmitButton({
  children,
  pendingLabel = "Submitting…",
  disabled,
  ...rest
}: SubmitButtonProps): React.ReactElement {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" disabled={disabled || pending} {...rest}>
      {pending ? pendingLabel : children}
    </Button>
  );
}
