import { requireUser } from "@/lib/auth";
import { getPublicMetadataEnv } from "@/lib/env";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";

// Auth-gated route group — must never be prerendered at build time.
export const dynamic = "force-dynamic";

export default async function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}): Promise<React.ReactElement> {
  await requireUser();
  const { NEXT_PUBLIC_APP_URL: baseUrl } = getPublicMetadataEnv();

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <Breadcrumbs baseUrl={baseUrl} className="mb-6" />
      {children}
    </div>
  );
}
