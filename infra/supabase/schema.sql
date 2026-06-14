-- F.A.B.L.E. Supabase schema — single-file, idempotent
-- Apply via: Supabase Dashboard -> SQL Editor -> paste -> Run
-- Project this is intended for: any fresh Supabase project (Postgres 17+).

-- =========================================================
-- 1. Extensions
-- =========================================================
create extension if not exists vector   with schema extensions;
create extension if not exists pgcrypto with schema extensions;

-- =========================================================
-- 2. Enums
-- =========================================================
do $$ begin
  create type public.provider_enum as enum ('openrouter','anthropic','openai','google');
exception when duplicate_object then null; end $$;
do $$ begin
  create type public.conn_type_enum as enum ('oauth','byok');
exception when duplicate_object then null; end $$;
do $$ begin
  create type public.memory_source_enum as enum ('chat_turn','adversarial_final','adversarial_step','document');
exception when duplicate_object then null; end $$;

-- =========================================================
-- 3. profiles (1:1 with auth.users) + auto-create trigger
-- =========================================================
create table if not exists public.profiles (
  id               uuid primary key references auth.users(id) on delete cascade,
  display_name     text,
  avatar_url       text,
  default_provider text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
alter table public.profiles enable row level security;
drop policy if exists profiles_select_own on public.profiles;
drop policy if exists profiles_update_own on public.profiles;
drop policy if exists profiles_insert_own on public.profiles;
create policy profiles_select_own on public.profiles
  for select using ((select auth.uid()) = id);
create policy profiles_update_own on public.profiles
  for update using ((select auth.uid()) = id) with check ((select auth.uid()) = id);
create policy profiles_insert_own on public.profiles
  for insert with check ((select auth.uid()) = id);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data->>'name', new.email))
  on conflict (id) do nothing;
  return new;
end;
$$;
-- Hardening: the trigger fires regardless of grants, but PostgREST exposes any
-- SECURITY DEFINER function in `public` as an RPC. Revoke EXECUTE so neither
-- anon nor authenticated can call it via the API.
revoke execute on function public.handle_new_user() from public;
revoke execute on function public.handle_new_user() from anon;
revoke execute on function public.handle_new_user() from authenticated;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- =========================================================
-- 4. provider_connections (AES-GCM ciphertext stored as base64 text)
-- =========================================================
create table if not exists public.provider_connections (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references auth.users(id) on delete cascade,
  provider          public.provider_enum not null,
  conn_type         public.conn_type_enum not null,
  label             text,
  secret_enc        text not null,           -- base64(nonce || ciphertext || tag)
  key_version       smallint not null default 1,
  last4             text,
  base_url          text,
  scopes            text,
  status            text not null default 'active',
  last_validated_at timestamptz,
  created_at        timestamptz not null default now(),
  unique (user_id, provider, conn_type, label)
);
create index if not exists provider_connections_user_active_idx
  on public.provider_connections (user_id, provider) where status = 'active';
alter table public.provider_connections enable row level security;
drop policy if exists provconn_select_own on public.provider_connections;
drop policy if exists provconn_modify_own on public.provider_connections;
create policy provconn_select_own on public.provider_connections
  for select using ((select auth.uid()) = user_id);
create policy provconn_modify_own on public.provider_connections
  for all using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

-- =========================================================
-- 5. oauth_states (PKCE; code_verifier kept server-side, short-lived)
-- =========================================================
create table if not exists public.oauth_states (
  state          uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users(id) on delete cascade,
  provider       public.provider_enum not null default 'openrouter',
  code_verifier  text not null,
  code_challenge text not null,
  redirect_after text,
  created_at     timestamptz not null default now(),
  expires_at     timestamptz not null default (now() + interval '10 minutes')
);
create index if not exists oauth_states_user_idx on public.oauth_states (user_id);
alter table public.oauth_states enable row level security;
drop policy if exists oauth_states_select_own on public.oauth_states;
drop policy if exists oauth_states_modify_own on public.oauth_states;
create policy oauth_states_select_own on public.oauth_states
  for select using ((select auth.uid()) = user_id);
create policy oauth_states_modify_own on public.oauth_states
  for all using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

-- =========================================================
-- 6. chat_sessions
-- =========================================================
create table if not exists public.chat_sessions (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade,
  title      text,
  domain     text not null default 'general',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists chat_sessions_user_idx on public.chat_sessions (user_id, updated_at desc);
alter table public.chat_sessions enable row level security;
drop policy if exists chat_sessions_select_own on public.chat_sessions;
drop policy if exists chat_sessions_modify_own on public.chat_sessions;
create policy chat_sessions_select_own on public.chat_sessions
  for select using ((select auth.uid()) = user_id);
create policy chat_sessions_modify_own on public.chat_sessions
  for all using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

-- =========================================================
-- 7. adversarial_runs (created before chat_messages — FK target)
-- =========================================================
create table if not exists public.adversarial_runs (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references auth.users(id) on delete cascade,
  session_id        uuid references public.chat_sessions(id) on delete cascade,
  task_id           text not null,
  domain            text not null,
  input_text        text not null,
  final_output      text,
  rounds_completed  int not null default 0,
  max_rounds        int not null,
  judge_verdict     text,
  judge_score       real,
  judge_rationale   text,
  unresolved_issues jsonb,
  scores            jsonb,
  pipeline          jsonb,
  model_used        text,
  created_at        timestamptz not null default now()
);
create index if not exists adversarial_runs_user_idx on public.adversarial_runs (user_id, created_at desc);
create index if not exists adversarial_runs_session_idx on public.adversarial_runs (session_id);
alter table public.adversarial_runs enable row level security;
drop policy if exists adv_runs_select_own on public.adversarial_runs;
drop policy if exists adv_runs_modify_own on public.adversarial_runs;
create policy adv_runs_select_own on public.adversarial_runs
  for select using ((select auth.uid()) = user_id);
create policy adv_runs_modify_own on public.adversarial_runs
  for all using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

-- =========================================================
-- 8. adversarial_messages
-- =========================================================
create table if not exists public.adversarial_messages (
  id         uuid primary key default gen_random_uuid(),
  run_id     uuid not null references public.adversarial_runs(id) on delete cascade,
  user_id    uuid not null references auth.users(id) on delete cascade,
  round      int not null default 0,
  seq        int not null,
  role       text not null,
  content    text not null,
  model      text,
  usage      jsonb,
  created_at timestamptz not null default now()
);
create index if not exists adversarial_messages_run_idx on public.adversarial_messages (run_id, seq);
alter table public.adversarial_messages enable row level security;
drop policy if exists adv_msgs_select_own on public.adversarial_messages;
drop policy if exists adv_msgs_modify_own on public.adversarial_messages;
create policy adv_msgs_select_own on public.adversarial_messages
  for select using ((select auth.uid()) = user_id);
create policy adv_msgs_modify_own on public.adversarial_messages
  for all using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

-- =========================================================
-- 9. chat_messages (FK to chat_sessions + adversarial_runs)
-- =========================================================
create table if not exists public.chat_messages (
  id                 uuid primary key default gen_random_uuid(),
  session_id         uuid not null references public.chat_sessions(id) on delete cascade,
  user_id            uuid not null references auth.users(id) on delete cascade,
  role               text not null,
  content            text not null,
  model_used         text,
  scores             jsonb,
  adversarial_run_id uuid references public.adversarial_runs(id) on delete set null,
  embedding          extensions.vector(384),
  created_at         timestamptz not null default now()
);
create index if not exists chat_messages_session_idx on public.chat_messages (session_id, created_at);
create index if not exists chat_messages_user_idx on public.chat_messages (user_id, created_at desc);
alter table public.chat_messages enable row level security;
drop policy if exists chat_msgs_select_own on public.chat_messages;
drop policy if exists chat_msgs_modify_own on public.chat_messages;
create policy chat_msgs_select_own on public.chat_messages
  for select using ((select auth.uid()) = user_id);
create policy chat_msgs_modify_own on public.chat_messages
  for all using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

-- =========================================================
-- 10. memory_chunks (unified semantic memory surface) + HNSW index
-- =========================================================
create table if not exists public.memory_chunks (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  source_type public.memory_source_enum not null,
  source_id   uuid,
  session_id  uuid references public.chat_sessions(id) on delete set null,
  domain      text,
  content     text not null,
  embedding   extensions.vector(384) not null,
  metadata    jsonb not null default '{}',
  cluster_id  uuid,
  created_at  timestamptz not null default now()
);
create index if not exists memory_chunks_user_idx on public.memory_chunks (user_id, created_at desc);
create index if not exists memory_chunks_embedding_idx
  on public.memory_chunks using hnsw (embedding extensions.vector_cosine_ops);
alter table public.memory_chunks enable row level security;
drop policy if exists memory_select_own on public.memory_chunks;
drop policy if exists memory_modify_own on public.memory_chunks;
create policy memory_select_own on public.memory_chunks
  for select using ((select auth.uid()) = user_id);
create policy memory_modify_own on public.memory_chunks
  for all using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

-- =========================================================
-- 11. match_memory_chunks — user-scoped cosine search
-- =========================================================
-- =========================================================
-- 12. guardrail_events — audit log for safety checks
--     Inserted by the backend (service-role); each user can read their own rows.
-- =========================================================
create table if not exists public.guardrail_events (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid references auth.users(id) on delete set null,  -- nullable: legacy mode
  stage        text not null,           -- 'pre_check' | 'post_check'
  verdict      text not null,           -- 'allow' | 'warn' | 'block'
  category     text,                    -- 'prompt_injection' | 'credential_exfil' | 'length' | 'classifier' | ...
  reason       text,
  layer        text,                    -- 'rules' | 'classifier'
  content_hash text not null,           -- sha256 of input; never store raw content
  task_id      text,
  created_at   timestamptz not null default now()
);
create index if not exists guardrail_events_user_idx on public.guardrail_events (user_id, created_at desc);
create index if not exists guardrail_events_verdict_idx on public.guardrail_events (verdict, created_at desc);

alter table public.guardrail_events enable row level security;
drop policy if exists guardrail_events_select_own on public.guardrail_events;
create policy guardrail_events_select_own on public.guardrail_events
  for select using ((select auth.uid()) = user_id);

-- =========================================================
-- 13. match_memory_chunks — user-scoped cosine search
-- =========================================================
create or replace function public.match_memory_chunks(
  p_user_id       uuid,
  query_embedding extensions.vector(384),
  match_count     int default 8
)
returns table (
  id          uuid,
  source_type public.memory_source_enum,
  source_id   uuid,
  session_id  uuid,
  domain      text,
  content     text,
  metadata    jsonb,
  similarity  real,
  created_at  timestamptz
)
language sql
stable
security invoker
set search_path = ''
as $$
  select
    mc.id, mc.source_type, mc.source_id, mc.session_id, mc.domain,
    mc.content, mc.metadata,
    (1 - (mc.embedding OPERATOR(extensions.<=>) query_embedding))::real as similarity,
    mc.created_at
  from public.memory_chunks mc
  where mc.user_id = p_user_id
  order by mc.embedding OPERATOR(extensions.<=>) query_embedding
  limit match_count;
$$;
-- F-007: deny direct RPC access from anon/authenticated roles. Memory search is
-- only reached via the service-role backend, which scopes by the caller's user_id.
revoke execute on function public.match_memory_chunks(uuid, extensions.vector, int)
  from public;


-- =========================================================
-- P4a. Privacy & Identity Foundation
-- =========================================================

-- 14. identities — pseudonymous-first with optional Supabase Auth link
create table if not exists public.identities (
  id              uuid primary key default gen_random_uuid(),
  pseudonymous    boolean not null default true,
  auth_user_id    uuid references auth.users(id) on delete set null,
  linked_at       timestamptz,
  consent_link    boolean not null default false,
  consent_memory  boolean not null default true,
  created_at      timestamptz not null default now(),
  last_seen_at    timestamptz not null default now()
);
create unique index if not exists identities_auth_user_idx
  on public.identities (auth_user_id) where auth_user_id is not null;

alter table public.identities enable row level security;
drop policy if exists identities_select_linked on public.identities;
drop policy if exists identities_modify_linked on public.identities;
-- Authed users may see / modify their linked identity row via RLS;
-- pseudonymous rows are accessed only via service-role + app-layer filter.
create policy identities_select_linked on public.identities
  for select using ((select auth.uid()) = auth_user_id);
create policy identities_modify_linked on public.identities
  for all using ((select auth.uid()) = auth_user_id)
       with check ((select auth.uid()) = auth_user_id);

-- 15. pii_entity_map — encrypted entity values per session/task, short TTL
create table if not exists public.pii_entity_map (
  id           uuid primary key default gen_random_uuid(),
  session_id   uuid not null references public.chat_sessions(id) on delete cascade,
  task_id      text not null,
  placeholder  text not null,
  entity_enc   text not null,
  entity_type  text not null,
  created_at   timestamptz not null default now(),
  expires_at   timestamptz not null default (now() + interval '7 days')
);
create index if not exists pii_entity_map_session_task_idx
  on public.pii_entity_map (session_id, task_id);
create index if not exists pii_entity_map_expires_idx
  on public.pii_entity_map (expires_at);

alter table public.pii_entity_map enable row level security;
-- Pure service-role access; no authenticated/anon path. No policies => no rows for anon/authed.

-- 16. Add identity_id to existing tables (nullable for backwards compat).
--     New writes populate identity_id; legacy rows keep user_id only.
alter table public.chat_sessions         add column if not exists identity_id uuid references public.identities(id) on delete cascade;
alter table public.chat_messages         add column if not exists identity_id uuid references public.identities(id) on delete cascade;
alter table public.adversarial_runs      add column if not exists identity_id uuid references public.identities(id) on delete cascade;
alter table public.adversarial_messages  add column if not exists identity_id uuid references public.identities(id) on delete cascade;
alter table public.memory_chunks         add column if not exists identity_id uuid references public.identities(id) on delete cascade;
alter table public.provider_connections  add column if not exists identity_id uuid references public.identities(id) on delete cascade;
alter table public.oauth_states          add column if not exists identity_id uuid references public.identities(id) on delete cascade;
alter table public.guardrail_events      add column if not exists identity_id uuid references public.identities(id) on delete cascade;

create index if not exists chat_sessions_identity_idx        on public.chat_sessions (identity_id, updated_at desc);
create index if not exists chat_messages_identity_idx        on public.chat_messages (identity_id, created_at desc);
create index if not exists adversarial_runs_identity_idx     on public.adversarial_runs (identity_id, created_at desc);
create index if not exists adversarial_messages_identity_idx on public.adversarial_messages (identity_id, created_at desc);
create index if not exists memory_chunks_identity_idx        on public.memory_chunks (identity_id, created_at desc);
create index if not exists provider_connections_identity_idx on public.provider_connections (identity_id, provider) where status = 'active';
create index if not exists oauth_states_identity_idx         on public.oauth_states (identity_id);
create index if not exists guardrail_events_identity_idx     on public.guardrail_events (identity_id, created_at desc);

-- 17. match_memory_chunks_by_identity — identity-scoped cosine search (P4a)
create or replace function public.match_memory_chunks_by_identity(
  p_identity_id   uuid,
  query_embedding extensions.vector(384),
  match_count     int default 8
)
returns table (
  id          uuid,
  source_type public.memory_source_enum,
  source_id   uuid,
  session_id  uuid,
  domain      text,
  content     text,
  metadata    jsonb,
  similarity  real,
  created_at  timestamptz
)
language sql
stable
security invoker
set search_path = ''
as $$
  select
    mc.id, mc.source_type, mc.source_id, mc.session_id, mc.domain,
    mc.content, mc.metadata,
    (1 - (mc.embedding OPERATOR(extensions.<=>) query_embedding))::real as similarity,
    mc.created_at
  from public.memory_chunks mc
  where mc.identity_id = p_identity_id
  order by mc.embedding OPERATOR(extensions.<=>) query_embedding
  limit match_count;
$$;
revoke execute on function public.match_memory_chunks_by_identity(uuid, extensions.vector, int)
  from public;

-- 18. pg_cron — sweep expired pii_entity_map rows (security: F-014 TTL enforcement)
-- Requires pg_cron extension enabled in Supabase dashboard (Database → Extensions → pg_cron).
-- Runs hourly; deletes rows where expires_at < now(). Safe to run multiple times.
select cron.schedule(
  'pii-entity-map-sweep',
  '0 * * * *',
  $$ delete from public.pii_entity_map where expires_at < now() $$
);

-- 19. pg_cron — sweep expired oauth_states rows (PKCE state tokens, short-lived)
select cron.schedule(
  'oauth-states-sweep',
  '*/15 * * * *',
  $$ delete from public.oauth_states where expires_at < now() $$
);

-- 20. revoked_identities — cookie/identity revocation list (F-001)
-- A row here means resolve_identity() must reject the identity and mint a fresh one.
create table if not exists public.revoked_identities (
  identity_id  uuid primary key references public.identities(id) on delete cascade,
  revoked_at   timestamptz not null default now(),
  reason       text
);
alter table public.revoked_identities enable row level security;
-- Service-role only: no anon/authenticated policies => no rows visible to those roles.
