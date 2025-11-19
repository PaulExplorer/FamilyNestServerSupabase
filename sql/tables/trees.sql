create table public.trees (
  id uuid not null default gen_random_uuid (),
  name text not null default 'New Tree'::text,
  owner_id uuid not null default auth.uid (),
  editor_ids uuid[] not null default '{}'::uuid[],
  viewer_ids uuid[] not null default '{}'::uuid[],
  is_public boolean not null default false,
  allow_file_uploads boolean not null default true,
  is_demo boolean not null default false,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint trees_pkey primary key (id),
  constraint trees_owner_id_fkey foreign KEY (owner_id) references auth.users (id) on delete CASCADE
) TABLESPACE pg_default;