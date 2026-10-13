"use client";

import { useTransition } from "react";
import { toast } from "sonner";

import { advanceOnboardingStep, skipOnboarding, saveOnboardingProfile } from "../api/actions";
import { ONBOARDING_STEPS, TOTAL_STEPS } from "../lib/steps";

interface Props {
  currentStep: number;
}

/** Progress dots shown at the top of the wizard. */
function StepIndicator({ current }: { current: number }): React.ReactElement {
  return (
    <div className="flex items-center justify-center gap-2" aria-label="Onboarding progress">
      {ONBOARDING_STEPS.map((step, i) => (
        <span
          key={step.id}
          className={[
            "size-2 rounded-full transition-all",
            i < current ? "bg-primary" : i === current ? "bg-primary size-2.5" : "bg-muted",
          ].join(" ")}
          aria-current={i === current ? "step" : undefined}
        />
      ))}
    </div>
  );
}

/** Step 0 — Welcome */
function WelcomeStep(): React.ReactElement {
  return (
    <div className="space-y-3 text-center">
      <span className="text-5xl">👋</span>
      <h2 className="text-foreground text-2xl font-bold">Welcome aboard!</h2>
      <p className="text-muted-foreground text-sm">
        This quick setup takes about 2 minutes. Let&apos;s get your workspace ready.
      </p>
    </div>
  );
}

/** Step 1 — Profile */
function ProfileStep(): React.ReactElement {
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <label htmlFor="full_name" className="text-foreground text-sm font-medium">
          Full name
        </label>
        <input
          id="full_name"
          name="full_name"
          type="text"
          autoComplete="name"
          required
          placeholder="Jane Smith"
          className="border-input bg-background placeholder:text-muted-foreground focus:ring-ring w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-none"
        />
      </div>
      <div className="space-y-1.5">
        <label htmlFor="username" className="text-foreground text-sm font-medium">
          Username
        </label>
        <div className="flex items-center">
          <span className="border-input bg-muted text-muted-foreground rounded-l-md border border-r-0 px-3 py-2 text-sm">
            @
          </span>
          <input
            id="username"
            name="username"
            type="text"
            autoComplete="username"
            required
            minLength={2}
            maxLength={32}
            placeholder="janesmith"
            pattern="[a-z0-9_-]+"
            className="border-input bg-background placeholder:text-muted-foreground focus:ring-ring flex-1 rounded-r-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-none"
          />
        </div>
        <p className="text-muted-foreground text-xs">Lowercase letters, numbers, _ and - only.</p>
      </div>
    </div>
  );
}

/** Step 2 — Workspace */
function WorkspaceStep(): React.ReactElement {
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <label htmlFor="workspace_name" className="text-foreground text-sm font-medium">
          Workspace name
        </label>
        <input
          id="workspace_name"
          name="workspace_name"
          type="text"
          required
          placeholder="Acme Inc."
          className="border-input bg-background placeholder:text-muted-foreground focus:ring-ring w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-none"
        />
        <p className="text-muted-foreground text-xs">
          This is how your team will see your workspace.
        </p>
      </div>
    </div>
  );
}

/** Step 3 — Plan selection (placeholder; hook up to Stripe in billing feature) */
function PlanStep(): React.ReactElement {
  const plans = [
    {
      id: "free",
      name: "Free",
      price: "$0/mo",
      features: ["Up to 3 projects", "5 GB storage", "Community support"],
    },
    {
      id: "pro",
      name: "Pro",
      price: "$12/mo",
      features: ["Unlimited projects", "50 GB storage", "Priority support"],
      recommended: true,
    },
  ];

  return (
    <div className="space-y-3">
      {plans.map((plan) => (
        <label
          key={plan.id}
          className={[
            "relative flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition-colors",
            plan.recommended ? "border-primary/50 bg-primary/5" : "border-border",
          ].join(" ")}
        >
          <input
            type="radio"
            name="plan"
            value={plan.id}
            defaultChecked={plan.id === "free"}
            className="accent-primary mt-0.5"
          />
          <div className="flex-1 space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-foreground text-sm font-semibold">{plan.name}</span>
              {plan.recommended && (
                <span className="bg-primary/10 text-primary rounded-full px-2 py-0.5 text-xs font-medium">
                  Recommended
                </span>
              )}
              <span className="text-muted-foreground ml-auto text-sm">{plan.price}</span>
            </div>
            <ul className="text-muted-foreground space-y-0.5 text-xs">
              {plan.features.map((f) => (
                <li key={f} className="flex items-center gap-1.5">
                  <span className="text-primary">✓</span> {f}
                </li>
              ))}
            </ul>
          </div>
        </label>
      ))}
    </div>
  );
}

/** Step 4 — Done */
function DoneStep(): React.ReactElement {
  return (
    <div className="space-y-3 text-center">
      <span className="text-5xl">🎉</span>
      <h2 className="text-foreground text-2xl font-bold">You&apos;re all set!</h2>
      <p className="text-muted-foreground text-sm">
        Your workspace is ready. Click &ldquo;Go to dashboard&rdquo; to start building.
      </p>
    </div>
  );
}

const STEP_COMPONENTS: Record<number, React.ReactElement> = {
  0: <WelcomeStep />,
  1: <ProfileStep />,
  2: <WorkspaceStep />,
  3: <PlanStep />,
  4: <DoneStep />,
};

/** Main onboarding wizard shell — rendered on /onboarding. */
export function OnboardingWizard({ currentStep }: Props): React.ReactElement {
  const [isPending, startTransition] = useTransition();
  const step = ONBOARDING_STEPS[currentStep];
  const isLast = currentStep >= TOTAL_STEPS - 1;

  function handleNext(formData?: FormData): void {
    startTransition(async () => {
      try {
        if (currentStep === 1 && formData) {
          await saveOnboardingProfile(formData);
        }
        await advanceOnboardingStep(currentStep);
      } catch {
        toast.error("Something went wrong. Please try again.");
      }
    });
  }

  return (
    <div className="bg-card border-border w-full max-w-md rounded-xl border p-8 shadow-sm">
      <div className="space-y-6">
        {/* Progress */}
        <StepIndicator current={currentStep} />

        {/* Step header */}
        <div className="space-y-1 text-center">
          <p className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
            Step {currentStep + 1} of {TOTAL_STEPS}
          </p>
          <h1 className="text-foreground text-xl font-bold">{step?.title}</h1>
          {step?.description && <p className="text-muted-foreground text-sm">{step.description}</p>}
        </div>

        {/* Step content — profile step needs a form wrapper */}
        {currentStep === 1 ? (
          <form id="step-form" action={(formData) => handleNext(formData)} className="space-y-4">
            {STEP_COMPONENTS[currentStep]}
          </form>
        ) : (
          <div>{STEP_COMPONENTS[currentStep] ?? null}</div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-between pt-2">
          <button
            type="button"
            onClick={() => startTransition(() => skipOnboarding())}
            disabled={isPending || isLast}
            className="text-muted-foreground hover:text-foreground text-sm transition-colors disabled:invisible"
          >
            Skip setup
          </button>

          {currentStep === 1 ? (
            <button
              type="submit"
              form="step-form"
              disabled={isPending}
              className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-5 py-2 text-sm font-medium transition-colors disabled:opacity-50"
            >
              {isPending ? "Saving…" : "Next →"}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => handleNext()}
              disabled={isPending}
              className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-5 py-2 text-sm font-medium transition-colors disabled:opacity-50"
            >
              {isPending ? "Saving…" : isLast ? "Go to dashboard →" : "Next →"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
