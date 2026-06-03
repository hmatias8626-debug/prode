create table if not exists api_cache (
  cache_key text primary key,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

-- Para simplificar en una app personal:
-- Si usás anon key, podés habilitar RLS y crear políticas de lectura/escritura.
-- Para empezar rápido, podés dejar RLS deshabilitado en esta tabla.
