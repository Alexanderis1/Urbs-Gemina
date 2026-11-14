-- Citizen reports, round 2 (Alessandro, 14 Nov 2026):
-- report types flood/sewer, pothole, traffic (incident, jam, bus, metro), construction site, public event;
-- every report is screened by Claude before it is stored, so only the "tools" edge function (service role) writes.

-- Old types move to the new ones.
alter table public.citizen_reports drop constraint if exists citizen_reports_category_check;
update public.citizen_reports set category = 'traffic' where category in ('congestion', 'emergency');
update public.citizen_reports set category = 'flood' where category in ('fire', 'other');
alter table public.citizen_reports add constraint citizen_reports_category_check
  check (category in ('flood', 'pothole', 'traffic', 'roadworks', 'public_event'));

alter table public.citizen_reports add column if not exists subtype text
  check (subtype is null or subtype in ('flood', 'sewer', 'incident', 'congestion', 'bus', 'metro'));
alter table public.citizen_reports add column if not exists screening jsonb not null default '{}'::jsonb;

-- A photo (with its own GPS/time check) is required except for public events and rejected reports
-- (a rejected report's photo is deleted at once).
alter table public.citizen_reports alter column photo_path drop not null;
alter table public.citizen_reports alter column photo_source drop not null;
alter table public.citizen_reports alter column photo_gps_distance_m drop not null;
alter table public.citizen_reports alter column photo_age_min drop not null;
alter table public.citizen_reports drop constraint if exists citizen_reports_photo_path_check;
alter table public.citizen_reports add constraint citizen_reports_photo_rule check (
  (photo_path is null and (category = 'public_event' or status = 'rejected'))
  or (photo_path ~ '^[0-9a-f-]{36}/[0-9a-f-]{36}\.jpg$' and photo_source is not null
      and photo_gps_distance_m is not null and photo_age_min is not null)
);

alter table public.citizen_reports drop constraint if exists citizen_reports_status_check;
alter table public.citizen_reports add constraint citizen_reports_status_check
  check (status in ('new', 'confirmed', 'dismissed', 'fixed', 'rejected'));

-- Only the edge function writes (after screening). Residents keep reading their own reports.
drop policy if exists "insert own report" on public.citizen_reports;

drop view if exists public.citizen_reports_staff;
create view public.citizen_reports_staff as
  select id, category, subtype, description, lon, lat, gps_accuracy_m, photo_path, photo_source,
         photo_gps_distance_m, photo_age_min, status, created_at,
         screening->>'photo' as screen_photo, screening->>'verdict' as screen_verdict,
         md5('urbs-signals:' || user_id::text) as reporter_key
  from public.citizen_reports
  where public.is_office() and status <> 'rejected'
    and (created_at > now() - interval '48 hours'
         or (category in ('pothole', 'roadworks', 'flood') and status in ('new', 'confirmed') and created_at > now() - interval '30 days'));

grant select on public.citizen_reports_staff to authenticated;

create or replace function public.set_report_status(report_id uuid, new_status text) returns void
  language plpgsql security definer set search_path = public as $$
begin
  if not public.is_office() then
    raise exception 'office tier only';
  end if;
  if new_status not in ('new', 'confirmed', 'dismissed', 'fixed') then
    raise exception 'unknown status %', new_status;
  end if;
  update public.citizen_reports set status = new_status where id = report_id and status <> 'rejected';
end;
$$;
