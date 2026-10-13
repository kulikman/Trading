"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { createApiKey, deleteApiKey } from "../api/actions";

interface ApiKeyRow {
  id: string;
  name: string;
  key_prefix: string;
  last_used_at: string | null;
  created_at: string;
  expires_at: string | null;
}

interface Props {
  initialKeys: ApiKeyRow[];
}

function formatDate(iso: string | null): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/** One-time reveal panel after key creation. */
function NewKeyReveal({
  rawKey,
  onDismiss,
}: {
  rawKey: string;
  onDismiss: () => void;
}): React.ReactElement {
  const [copied, setCopied] = useState(false);

  async function copy(): Promise<void> {
    await navigator.clipboard.writeText(rawKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="border-primary/30 bg-primary/5 space-y-3 rounded-lg border p-4">
      <p className="text-foreground text-sm font-semibold">
        ⚠️ Copy this key now — it won&apos;t be shown again.
      </p>
      <div className="flex items-center gap-2">
        <code className="bg-muted text-foreground flex-1 rounded px-3 py-2 font-mono text-xs break-all">
          {rawKey}
        </code>
        <button
          type="button"
          onClick={copy}
          className="border-border bg-background hover:bg-muted shrink-0 rounded-md border px-3 py-2 text-xs font-medium transition-colors"
        >
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        className="text-muted-foreground hover:text-foreground text-xs underline transition-colors"
      >
        I&apos;ve saved my key — dismiss
      </button>
    </div>
  );
}

/** The full API keys manager component. */
export function ApiKeysManager({ initialKeys }: Props): React.ReactElement {
  const [keys, setKeys] = useState<ApiKeyRow[]>(initialKeys);
  const [newKeyName, setNewKeyName] = useState("");
  const [revealedKey, setRevealedKey] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleCreate(): void {
    if (!newKeyName.trim()) {
      toast.error("Enter a name for your API key.");
      return;
    }

    startTransition(async () => {
      try {
        const result = await createApiKey(newKeyName.trim());
        setRevealedKey(result.rawKey);
        setNewKeyName("");
        // Optimistic add (no hash — hash is never in the client)
        setKeys((prev) => [
          {
            id: result.id,
            name: newKeyName.trim(),
            key_prefix: result.rawKey.slice(0, 12),
            last_used_at: null,
            created_at: new Date().toISOString(),
            expires_at: null,
          },
          ...prev,
        ]);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to create key.");
      }
    });
  }

  function handleDelete(keyId: string, keyName: string): void {
    if (!confirm(`Delete API key "${keyName}"? Any integrations using it will stop working.`))
      return;

    startTransition(async () => {
      try {
        await deleteApiKey(keyId);
        setKeys((prev) => prev.filter((k) => k.id !== keyId));
        toast.success("API key deleted.");
      } catch {
        toast.error("Failed to delete key.");
      }
    });
  }

  return (
    <div className="space-y-6">
      {/* Revealed key banner */}
      {revealedKey && <NewKeyReveal rawKey={revealedKey} onDismiss={() => setRevealedKey(null)} />}

      {/* Create new key */}
      <div className="flex gap-2">
        <input
          type="text"
          value={newKeyName}
          onChange={(e) => setNewKeyName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          placeholder="Key name, e.g. Production"
          maxLength={64}
          className="border-input bg-background placeholder:text-muted-foreground focus:ring-ring flex-1 rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-none"
        />
        <button
          type="button"
          onClick={handleCreate}
          disabled={isPending || !newKeyName.trim()}
          className="bg-primary text-primary-foreground hover:bg-primary/90 shrink-0 rounded-md px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50"
        >
          {isPending ? "Creating…" : "Create key"}
        </button>
      </div>

      {/* Keys table */}
      {keys.length === 0 ? (
        <p className="text-muted-foreground py-6 text-center text-sm">
          No API keys yet. Create one above.
        </p>
      ) : (
        <div className="border-border divide-border divide-y overflow-hidden rounded-xl border">
          {keys.map((key) => (
            <div key={key.id} className="flex items-center gap-4 px-4 py-3">
              <div className="min-w-0 flex-1 space-y-0.5">
                <p className="text-foreground text-sm font-medium">{key.name}</p>
                <div className="text-muted-foreground flex items-center gap-3 text-xs">
                  <code className="bg-muted rounded px-1.5 py-0.5 font-mono">
                    {key.key_prefix}…
                  </code>
                  <span>Created {formatDate(key.created_at)}</span>
                  <span>Last used {formatDate(key.last_used_at)}</span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => handleDelete(key.id, key.name)}
                disabled={isPending}
                className="text-muted-foreground hover:text-destructive shrink-0 text-sm transition-colors disabled:opacity-50"
              >
                Revoke
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
