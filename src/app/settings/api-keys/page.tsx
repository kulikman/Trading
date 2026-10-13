import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { ApiKeysManager } from "@/features/api-keys";

export const metadata = { title: "API Keys" };

export default async function ApiKeysPage(): Promise<React.ReactElement> {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const { data: keys } = await supabase
    .from("api_keys")
    .select("id, name, key_prefix, last_used_at, created_at, expires_at")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false });

  return (
    <div className="mx-auto max-w-2xl space-y-8 px-4 py-10">
      <div>
        <h1 className="text-foreground text-2xl font-bold">API Keys</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Use API keys to authenticate requests from your server-side integrations. Keys are shown
          once — store them in a secret manager, not in source code.
        </p>
      </div>

      <ApiKeysManager initialKeys={keys ?? []} />

      <div className="border-border bg-muted/30 space-y-2 rounded-lg border p-4 text-xs">
        <p className="text-foreground font-semibold">Using your API key</p>
        <p className="text-muted-foreground">
          Pass the key in the <code className="bg-muted rounded px-1">x-api-key</code> header:
        </p>
        <pre className="bg-muted text-foreground overflow-x-auto rounded px-3 py-2 text-xs">
          {`curl https://your-app.com/api/endpoint \\
  -H "x-api-key: sk_live_..."`}
        </pre>
      </div>
    </div>
  );
}
