-- Citizen reports ("segnalazioni"): a resident signs in (demo SPID on top of Lovable Cloud auth) and sends
-- a category, a photo, a short text and the device GPS. Alessandro (14 Nov 2026): a report needs the photo's
-- own location and the device GPS turned on, so both checks are NOT NULL here.
--
-- Privacy: no name, e-mail or phone is stored. The browser reads the photo's GPS and time, keeps only the
-- distance to the device GPS and the age, then re-encodes the photo without any EXIF before upload.
-- Staff never see who reported: the staff view exposes an opaque reporter key (one per account) only.

create table if not exists public.citizen_reports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  category text not null check (category in ('congestion', 'flood', 'fire', 'emergency', 'other')),
  description text not null default '' check (char_length(description) <= 280),
  lon double precision not null check (lon between 12.0 and 13.1),
  lat double precision not null check (lat between 41.4 and 42.4),
  gps_accuracy_m real check (gps_accuracy_m >= 0),
  photo_path text not null check (photo_path ~ '^[0-9a-f-]{36}/[0-9a-f-]{36}\.jpg$'),
  photo_source text not null check (photo_source in ('camera', 'gallery')),
  photo_gps_distance_m real not null check (photo_gps_distance_m >= 0),
  photo_age_min real not null,
  status text not null default 'new' check (status in ('new', 'confirmed', 'dismissed')),
  created_at timestamptz not null default now()
);

create index if not exists citizen_reports_created_at on public.citizen_reports (created_at desc);

alter table public.citizen_reports enable row level security;

-- A resident sends reports as themselves and sees only their own.
create policy "insert own report" on public.citizen_reports
  for insert to authenticated with check (auth.uid() = user_id and status = 'new');
create policy "read own reports" on public.citizen_reports
  for select to authenticated using (auth.uid() = user_id);

create or replace function public.is_office() returns boolean
  language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.user_roles r where r.user_id = auth.uid() and r.tier = 'office');
$$;

-- Staff view: last 48 hours, no user id. reporter_key is a one-way key so that one account counts once.
create or replace view public.citizen_reports_staff as
  select id, category, description, lon, lat, gps_accuracy_m, photo_path, photo_source,
         photo_gps_distance_m, photo_age_min, status, created_at,
         md5('urbs-signals:' || user_id::text) as reporter_key
  from public.citizen_reports
  where public.is_office() and created_at > now() - interval '48 hours';

grant select on public.citizen_reports_staff to authenticated;

-- Staff confirm or dismiss a report (the only change they can make).
create or replace function public.set_report_status(report_id uuid, new_status text) returns void
  language plpgsql security definer set search_path = public as $$
begin
  if not public.is_office() then
    raise exception 'office tier only';
  end if;
  if new_status not in ('new', 'confirmed', 'dismissed') then
    raise exception 'unknown status %', new_status;
  end if;
  update public.citizen_reports set status = new_status where id = report_id;
end;
$$;

-- Photos: private bucket, one folder per account. Staff read them through short-lived signed URLs.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('report-photos', 'report-photos', false, 5242880, array['image/jpeg'])
on conflict (id) do nothing;

create policy "upload own report photo" on storage.objects
  for insert to authenticated
  with check (bucket_id = 'report-photos' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "read own report photo" on storage.objects
  for select to authenticated
  using (bucket_id = 'report-photos' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "office reads report photos" on storage.objects
  for select to authenticated
  using (bucket_id = 'report-photos' and public.is_office());
