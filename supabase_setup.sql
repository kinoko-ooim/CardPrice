create table if not exists public.card_app_state (
  id text primary key,
  payload jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default timezone('utc', now())
);

create or replace function public.set_card_app_state_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists set_card_app_state_updated_at on public.card_app_state;
create trigger set_card_app_state_updated_at
before update on public.card_app_state
for each row
execute function public.set_card_app_state_updated_at();

alter table public.card_app_state enable row level security;

drop policy if exists "Allow public read card app state" on public.card_app_state;
create policy "Allow public read card app state"
on public.card_app_state
for select
to anon, authenticated
using (true);

drop policy if exists "Allow public insert card app state" on public.card_app_state;
create policy "Allow public insert card app state"
on public.card_app_state
for insert
to anon, authenticated
with check (true);

drop policy if exists "Allow public update card app state" on public.card_app_state;
create policy "Allow public update card app state"
on public.card_app_state
for update
to anon, authenticated
using (true)
with check (true);

insert into public.card_app_state (id, payload)
values ('main', '[]'::jsonb)
on conflict (id) do nothing;

insert into storage.buckets (id, name, public)
values ('card-images', 'card-images', true)
on conflict (id) do update
set public = true;

drop policy if exists "Allow public read card images" on storage.objects;
create policy "Allow public read card images"
on storage.objects
for select
to public
using (bucket_id = 'card-images');

drop policy if exists "Allow public upload card images" on storage.objects;
create policy "Allow public upload card images"
on storage.objects
for insert
to public
with check (bucket_id = 'card-images');

drop policy if exists "Allow public update card images" on storage.objects;
create policy "Allow public update card images"
on storage.objects
for update
to public
using (bucket_id = 'card-images')
with check (bucket_id = 'card-images');
