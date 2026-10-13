import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  completeOnboarding: vi.fn(),
  createClient: vi.fn(),
  redirect: vi.fn((url: string) => {
    throw new Error(`NEXT_REDIRECT:${url}`);
  }),
  revalidatePath: vi.fn(),
  setOnboardingStep: vi.fn(),
  updateOnboardingProfile: vi.fn(),
}));

vi.mock("@/lib/supabase/server", () => ({
  createClient: mocks.createClient,
}));

vi.mock("next/cache", () => ({
  revalidatePath: mocks.revalidatePath,
}));

vi.mock("next/navigation", () => ({
  redirect: mocks.redirect,
}));

vi.mock("../lib/profile", () => ({
  completeOnboarding: mocks.completeOnboarding,
  setOnboardingStep: mocks.setOnboardingStep,
  updateOnboardingProfile: mocks.updateOnboardingProfile,
}));

import { advanceOnboardingStep, saveOnboardingProfile, skipOnboarding } from "./actions";

function mockUser(user: { id: string } | null): void {
  mocks.createClient.mockResolvedValue({
    auth: {
      getUser: vi.fn().mockResolvedValue({ data: { user } }),
    },
  });
}

describe("onboarding actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUser({ id: "user-1" });
  });

  it("advances onboarding through the profile helper", async () => {
    await advanceOnboardingStep(0);

    expect(mocks.setOnboardingStep).toHaveBeenCalledWith({
      userId: "user-1",
      step: 1,
      completed: false,
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/onboarding");
    expect(mocks.redirect).not.toHaveBeenCalled();
  });

  it("redirects to dashboard when the last step is reached", async () => {
    await expect(advanceOnboardingStep(3)).rejects.toThrow("NEXT_REDIRECT:/dashboard");

    expect(mocks.setOnboardingStep).toHaveBeenCalledWith({
      userId: "user-1",
      step: 4,
      completed: true,
    });
  });

  it("skips onboarding for the current user", async () => {
    await expect(skipOnboarding()).rejects.toThrow("NEXT_REDIRECT:/dashboard");

    expect(mocks.completeOnboarding).toHaveBeenCalledWith("user-1");
  });

  it("saves trimmed profile data", async () => {
    const formData = new FormData();
    formData.set("full_name", " Ada Lovelace ");
    formData.set("username", " ada ");

    await saveOnboardingProfile(formData);

    expect(mocks.updateOnboardingProfile).toHaveBeenCalledWith("user-1", {
      fullName: "Ada Lovelace",
      username: "ada",
    });
  });

  it("does not write incomplete profile data", async () => {
    const formData = new FormData();
    formData.set("full_name", "Ada Lovelace");

    await saveOnboardingProfile(formData);

    expect(mocks.updateOnboardingProfile).not.toHaveBeenCalled();
  });

  it("redirects signed-out users to login", async () => {
    mockUser(null);

    await expect(advanceOnboardingStep(0)).rejects.toThrow("NEXT_REDIRECT:/login");
    expect(mocks.setOnboardingStep).not.toHaveBeenCalled();
  });
});
