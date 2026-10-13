"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { getClientEnv } from "@/lib/env";
import { createOrgAction } from "../api/actions";

export function OrgCreateForm(): React.ReactElement {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const router = useRouter();

  /** Auto-derive slug from name: lowercase, spaces → hyphens, strip non-alphanum. */
  function handleNameChange(value: string): void {
    setName(value);
    setSlug(
      value
        .toLowerCase()
        .replace(/\s+/g, "-")
        .replace(/[^a-z0-9-]/g, "")
        .slice(0, 48)
    );
  }

  function handleSubmit(e: React.FormEvent): void {
    e.preventDefault();
    setError(null);

    startTransition(async () => {
      const result = await createOrgAction({ name, slug });
      if (!result.ok) {
        setError(result.error);
        return;
      }
      router.refresh();
      setName("");
      setSlug("");
    });
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <label htmlFor="org-name" className="text-foreground text-sm font-medium">
          Name
        </label>
        <input
          id="org-name"
          type="text"
          value={name}
          onChange={(e) => handleNameChange(e.target.value)}
          placeholder="Acme Inc."
          required
          minLength={1}
          maxLength={100}
          className="border-input bg-background focus:ring-ring w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="org-slug" className="text-foreground text-sm font-medium">
          Slug
        </label>
        <div className="border-input bg-muted flex items-center rounded-md border">
          <span className="text-muted-foreground px-3 py-2 text-sm select-none">
            {new URL(getClientEnv().NEXT_PUBLIC_APP_URL).host}/
          </span>
          <input
            id="org-slug"
            type="text"
            value={slug}
            onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
            placeholder="acme-inc"
            required
            minLength={2}
            maxLength={48}
            pattern="[a-z0-9-]+"
            className="bg-background focus:ring-ring min-w-0 flex-1 rounded-r-md px-3 py-2 text-sm focus:ring-2 focus:outline-none"
          />
        </div>
        <p className="text-muted-foreground text-xs">
          Lowercase letters, numbers, and hyphens only.
        </p>
      </div>

      {error && <p className="text-destructive text-sm">{error}</p>}

      <Button type="submit" disabled={isPending || !name.trim() || slug.length < 2}>
        {isPending ? "Creating…" : "Create organization"}
      </Button>
    </form>
  );
}
