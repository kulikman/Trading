import Link from "next/link";

import { siteConfig } from "@/config/site";
import { ROUTES } from "@/lib/constants";
import { Button } from "@/components/ui/button";

/**
 * Landing page. Replace with your product's marketing surface when forking.
 * Uses theme tokens (bg-background, text-foreground, …) so dark mode and
 * tenant theming stay automatic.
 */
export default function Home(): React.ReactElement {
  return (
    <section className="bg-muted/40 flex flex-1 items-center justify-center px-6 py-16">
      <div className="border-border bg-card w-full max-w-3xl rounded-2xl border p-10 shadow-sm">
        <div className="flex flex-col gap-6">
          <span className="bg-primary text-primary-foreground w-fit rounded-full px-3 py-1 text-xs font-semibold tracking-wide uppercase">
            {siteConfig.name}
          </span>
          <h1 className="text-foreground text-3xl font-semibold tracking-tight sm:text-4xl">
            A consistent base for Next.js apps with Supabase and Tailwind.
          </h1>
          <p className="text-muted-foreground max-w-2xl text-base leading-7 sm:text-lg">
            Fork this repo, run{" "}
            <code className="bg-muted rounded px-1.5 py-0.5 text-sm">pnpm post-clone</code>, and
            ship your product — the template stays product-agnostic.
          </p>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Button size="lg" asChild>
              <Link href={ROUTES.dashboard}>Open dashboard</Link>
            </Button>
            <Button size="lg" variant="outline" asChild>
              <a href={siteConfig.links.github} target="_blank" rel="noopener noreferrer">
                Repository
              </a>
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
