create table public.tree_invitations (
  token uuid not null default gen_random_uuid (),
  tree_id uuid not null default gen_random_uuid (),
  role text not null,
  expires_at timestamp with time zone not null,
  used_by_users uuid[] not null,
  usage_limit integer null,
  created_at timestamp with time zone not null default now(),
  constraint tree_invitations_pkey primary key (token, tree_id),
  constraint tree_invitations_tree_id_fkey foreign KEY (tree_id) references trees (id) on delete CASCADE
) TABLESPACE pg_default;