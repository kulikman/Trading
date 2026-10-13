import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import {
  completeOnboarding,
  getOnboardingStatus,
  setOnboardingStep,
  updateOnboardingProfile,
} from "./profile";

const mocks = vi.hoisted(() => {
  const eq = vi.fn();
  const single = vi.fn();
  const select = vi.fn(() => ({ eq: vi.fn(() => ({ single })) }));
  const update = vi.fn(() => ({ eq }));
  const from = vi.fn(() => ({ select, update }));
  const createClient = vi.fn(async () => ({ from }));

  return { createClient, eq, from, select, single, update };
});

vi.mock("@/lib/supabase/server", () => ({
  createClient: mocks.createClient,
}));

describe("onboarding profile helpers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("reads onboarding status for a user", async () => {
    mocks.single.mockResolvedValueOnce({
      data: { onboarding_completed: false, onboarding_step: 2 },
    });

    await expect(getOnboardingStatus("user-1")).resolves.toEqual({
      completed: false,
      step: 2,
    });

    expect(mocks.from).toHaveBeenCalledWith("profiles");
    expect(mocks.select).toHaveBeenCalledWith("onboarding_completed, onboarding_step");
  });

  it("defaults missing onboarding status to the first step", async () => {
    mocks.single.mockResolvedValueOnce({ data: null });

    await expect(getOnboardingStatus("user-1")).resolves.toEqual({
      completed: false,
      step: 0,
    });
  });

  it("sets the current onboarding step", async () => {
    await setOnboardingStep({ userId: "user-1", step: 2, completed: false });

    expect(mocks.from).toHaveBeenCalledWith("profiles");
    expect(mocks.update).toHaveBeenCalledWith({ onboarding_step: 2 });
    expect(mocks.eq).toHaveBeenCalledWith("id", "user-1");
  });

  it("marks onboarding as completed with the final step", async () => {
    await setOnboardingStep({ userId: "user-1", step: 3, completed: true });

    expect(mocks.update).toHaveBeenCalledWith({
      onboarding_step: 3,
      onboarding_completed: true,
    });
  });

  it("can complete onboarding without changing the current step", async () => {
    await completeOnboarding("user-1");

    expect(mocks.update).toHaveBeenCalledWith({ onboarding_completed: true });
    expect(mocks.eq).toHaveBeenCalledWith("id", "user-1");
  });

  it("updates collected profile data", async () => {
    await updateOnboardingProfile("user-1", { fullName: "Ada Lovelace", username: "ada" });

    expect(mocks.update).toHaveBeenCalledWith({
      full_name: "Ada Lovelace",
      username: "ada",
    });
    expect(mocks.eq).toHaveBeenCalledWith("id", "user-1");
  });
});
