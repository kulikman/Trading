export interface RouteDefinition {
  href: string;
  label: string;
  title: string;
  description?: string;
  public?: boolean;
  sitemap?: boolean;
  aliases?: readonly string[];
  children?: RouteTree;
}

export type RouteTree = Record<string, RouteDefinition>;

export const routes = {
  home: {
    href: "/",
    label: "Home",
    title: "Home",
    public: true,
    sitemap: true,
  },
  pricing: {
    href: "/pricing",
    label: "Pricing",
    title: "Pricing",
    description: "Simple, transparent pricing.",
    public: true,
    sitemap: true,
  },
  login: {
    href: "/login",
    label: "Sign in",
    title: "Sign in",
    public: true,
  },
  signup: {
    href: "/signup",
    label: "Sign up",
    title: "Create an account",
    public: true,
  },
  forgotPassword: {
    href: "/forgot-password",
    label: "Forgot password",
    title: "Forgot password",
    public: true,
  },
  resetPassword: {
    href: "/reset-password",
    label: "Reset password",
    title: "Reset password",
    public: true,
  },
  dashboard: {
    href: "/dashboard",
    label: "Dashboard",
    title: "Dashboard",
  },
  onboarding: {
    href: "/onboarding",
    label: "Onboarding",
    title: "Onboarding",
  },
  settings: {
    href: "/settings",
    label: "Settings",
    title: "Settings",
    children: {
      billing: {
        href: "/settings/billing",
        label: "Billing",
        title: "Billing",
      },
      usage: {
        href: "/settings/usage",
        label: "Usage",
        title: "Usage",
      },
      apiKeys: {
        href: "/settings/api-keys",
        label: "API Keys",
        title: "API Keys",
      },
      organization: {
        href: "/settings/organization",
        label: "Organization",
        title: "Organizations",
        aliases: ["/settings/org"],
      },
    },
  },
} as const satisfies RouteTree;
