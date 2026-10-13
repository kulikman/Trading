-- 0008_harden_api_keys.sql
-- Defense-in-depth for API keys: authenticated users may rename their own key,
-- but must not be able to rewrite the hash, owner, prefix, timestamps, or expiry.

create or replace function public.prevent_api_key_secret_updates()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if auth.role() <> 'service_role' then
    if new.user_id is distinct from old.user_id
      or new.key_hash is distinct from old.key_hash
      or new.key_prefix is distinct from old.key_prefix
      or new.last_used_at is distinct from old.last_used_at
      or new.expires_at is distinct from old.expires_at
      or new.created_at is distinct from old.created_at
    then
      raise exception 'Only API key name can be updated by users' using errcode = '42501';
    end if;
  end if;

  return new;
end;
$$;

drop trigger if exists api_keys_prevent_secret_updates on public.api_keys;

create trigger api_keys_prevent_secret_updates
  before update on public.api_keys
  for each row execute function public.prevent_api_key_secret_updates();
