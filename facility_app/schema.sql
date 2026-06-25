-- Facility Assessment Snapshot - Supabase schema
-- Run this entire file in your Supabase SQL editor before first use.

-- Main table: one row per CCN, always current (upserted on every fetch)
create table if not exists facility_assessments (
    ccn                     text primary key,
    state                   text,

    -- name handling: kept separate so override never clobbers the source value
    facility_name_api       text,
    facility_name_override  text,
    facility_name_display   text,

    -- CMS API fields (Provider Information)
    location                text,
    census_capacity         integer,
    overall_rating          smallint,
    health_inspection_rating smallint,
    staffing_rating         smallint,
    quality_rating          smallint,

    -- manual operational inputs
    emr                     text,
    current_census          integer,
    type_of_patient         text,
    previous_coverage       text,
    previous_provider_performance text,
    medical_coverage        text,

    -- 12 hospitalization/ED metrics + state/national averages (bonus)
    metrics                 jsonb,

    -- full raw CMS payload at fetch time, for audit/debug
    raw_api_snapshot        jsonb,

    created_at              timestamptz default now(),
    updated_at              timestamptz default now()
);

create index if not exists idx_assessments_updated_at
    on facility_assessments (updated_at desc);

-- Audit table: previous versions, written automatically on update
create table if not exists facility_assessments_history (
    id          uuid primary key default gen_random_uuid(),
    ccn         text not null,
    snapshot    jsonb not null,
    archived_at timestamptz default now()
);

create index if not exists idx_history_ccn
    on facility_assessments_history (ccn);

-- Trigger: before any update to facility_assessments, archive the old row
create or replace function archive_facility_assessment()
returns trigger as $$
begin
    insert into facility_assessments_history (ccn, snapshot)
    values (OLD.ccn, to_jsonb(OLD));
    return NEW;
end;
$$ language plpgsql;

drop trigger if exists trg_archive_facility_assessment on facility_assessments;
create trigger trg_archive_facility_assessment
before update on facility_assessments
for each row
execute function archive_facility_assessment();

-- Keep updated_at fresh automatically
create or replace function set_updated_at()
returns trigger as $$
begin
    NEW.updated_at = now();
    return NEW;
end;
$$ language plpgsql;

drop trigger if exists trg_set_updated_at on facility_assessments;
create trigger trg_set_updated_at
before update on facility_assessments
for each row
execute function set_updated_at();
