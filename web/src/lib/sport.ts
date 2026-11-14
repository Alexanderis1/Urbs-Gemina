import { latLngToCell } from "h3-js";
import { texts, tr } from "@/lib/i18n";
// Shapes and helpers for the Sport screen (Challenge 04). Shapes follow the sports workstream's
// sports_facilities / sport_deserts tools (twin/modules/sports, PR #5).

export type FieldStatus = "official" | "open_data" | "web_unverified" | "manager_confirmed" | "simulated" | "not_known";

export interface FieldSource {
  source: string;
  record_id?: string;
  url?: string;
  retrieved_at?: string;
  confidence?: number;
  quote?: string;
}

export interface SportField {
  value: unknown;
  status: FieldStatus;
  sources: FieldSource[];
  /** Text the UI must show next to the value, e.g. "from the web, unverified". */
  label?: string;
}

export interface SportFeature {
  type: "Feature";
  id: string;
  geometry: { type: "Point"; coordinates: [number, number] } | null;
  properties: {
    facility_id: string;
    name: string | null;
    kind: string;
    municipio: string | null;
    disciplines: string[];
    /** public | school | private | unclassified */
    type?: FacilityType;
    /** true / false, or null when no source states it. */
    accessible?: boolean | null;
    /** OSM-style access: yes / customers / private / no, or null when not known. */
    access?: FacilityAccess | null;
    /** true when the source marks the facility as closed or disused. */
    closed?: boolean;
    fields: Record<string, SportField>;
    discipline_details: Record<string, SportField>;
    synthetic: boolean;
  };
}

export interface ZoneRow {
  zone: string;
  residents: number;
  children: number;
  residents_uncovered: number;
  children_uncovered: number;
  uncovered_share: number;
  desert: boolean;
  /** Population-weighted centre [lon, lat]. */
  centroid?: [number, number];
}

export interface Coverage {
  discipline: string;
  reach_m: number;
  facilities_offering: number;
  residents_total: number;
  residents_uncovered: number;
  children_total: number;
  children_uncovered: number;
  zones: ZoneRow[];
  desert_zones: string[];
}

export interface WhatIf {
  baseline: Coverage;
  variant: Coverage;
  added: string[];
  delta: { residents_newly_covered: number; children_newly_covered: number };
}

const T = texts({
  en: {
    status: {
      official: "official",
      open_data: "open data",
      web_unverified: "from the web, unverified",
      manager_confirmed: "confirmed by manager",
      simulated: "simulated",
      not_known: "not known",
    } as Record<FieldStatus, string>,
    typeNotKnown: "type not known",
    types: { public: "public", school: "school", private: "private", unclassified: "type not known" } as Record<FacilityType, string>,
    access: {
      yes: "open to the public",
      customers: "customers only",
      private: "private",
      no: "no access",
    } as Record<FacilityAccess, string>,
    accessNotKnown: "access not known",
    fieldCannotBeEdited: (field: string) => `Field "${field}" cannot be edited`,
    badAccount: "account_ref must be an organisational account, e.g. org:asd-roma",
  },
  it: {
    status: {
      official: "ufficiale",
      open_data: "dati aperti",
      web_unverified: "dal web, non verificato",
      manager_confirmed: "confermato dal gestore",
      simulated: "simulato",
      not_known: "non noto",
    } as Record<FieldStatus, string>,
    typeNotKnown: "tipo non noto",
    types: { public: "pubblico", school: "scolastico", private: "privato", unclassified: "tipo non noto" } as Record<FacilityType, string>,
    access: {
      yes: "aperto al pubblico",
      customers: "solo clienti",
      private: "privato",
      no: "nessun accesso",
    } as Record<FacilityAccess, string>,
    accessNotKnown: "accesso non noto",
    fieldCannotBeEdited: (field: string) => `Il campo "${field}" non si può modificare`,
    badAccount: "account_ref deve essere un account di un'organizzazione, per esempio org:asd-roma",
  },
});

export function fieldLabel(f: SportField): string {
  return f.label ?? tr(T).status[f.status];
}

export type FacilityType = "public" | "school" | "private" | "unclassified";
export const FACILITY_TYPES: FacilityType[] = ["public", "school", "private", "unclassified"];

export function typeLabel(t: FacilityType | undefined): string {
  const x = tr(T);
  return !t || t === "unclassified" ? x.typeNotKnown : x.types[t] ?? t;
}

export interface SportFilter {
  type?: FacilityType;
  discipline?: string;
  kind?: string;
  municipio?: string;
  accessibleOnly?: boolean;
}

export function filterFacilities(list: SportFeature[], flt: SportFilter): SportFeature[] {
  return list.filter((f) => {
    const p = f.properties;
    if (flt.discipline && !p.disciplines.includes(flt.discipline)) return false;
    if (flt.kind && p.kind !== flt.kind) return false;
    if (flt.municipio && p.municipio !== flt.municipio) return false;
    if (flt.type && (p.type ?? "unclassified") !== flt.type) return false;
    if (flt.accessibleOnly && p.accessible !== true) return false;
    return true;
  });
}

export const EDITABLE_FIELDS = ["disciplines", "hours", "accessibility", "contact", "name"] as const;

export interface ManagerUpdate {
  facility_id: string;
  field: string;
  value: unknown;
  account_ref: string;
  confirmed_at: string;
}

/** account_ref must be an organisational account ("org:<slug>"), never a person's name. */
export function buildManagerUpdate(
  facilityId: string,
  field: string,
  value: unknown,
  accountRef: string,
  confirmedAt: string,
): ManagerUpdate {
  if (!(EDITABLE_FIELDS as readonly string[]).includes(field)) throw new Error(tr(T).fieldCannotBeEdited(field));
  if (!/^org:[a-z0-9-]+$/.test(accountRef)) throw new Error(tr(T).badAccount);
  return { facility_id: facilityId, field, value, account_ref: accountRef, confirmed_at: confirmedAt };
}

/** 44 official facilities have no name: show the kind plus the address instead. */
export function displayName(f: SportFeature): string {
  const p = f.properties;
  if (p.name && p.name.trim()) return p.name;
  const addr = p.fields.address?.value;
  const kind = p.kind.replace(/_/g, " ");
  return typeof addr === "string" && addr ? `${kind}, ${addr}` : kind;
}

export type FacilityAccess = "yes" | "customers" | "private" | "no";

export function accessLabel(a: FacilityAccess | null | undefined): string {
  const x = tr(T);
  return a ? x.access[a] ?? a : x.accessNotKnown;
}

/** Closed, private or no-access facilities are greyed out and do not count in sport_coverage. */
export function isInactive(f: SportFeature): boolean {
  const p = f.properties;
  return p.closed === true || p.access === "private" || p.access === "no";
}

export const CLUSTER_MIN_FEATURES = 1500;
export const CLUSTER_MAX_ZOOM = 13;

export function shouldCluster(count: number, zoom: number): boolean {
  return count >= CLUSTER_MIN_FEATURES && zoom < CLUSTER_MAX_ZOOM;
}

export interface FacilityCell {
  h3: string;
  count: number;
  active: number;
}

export function clusterH3(list: SportFeature[], res: number): FacilityCell[] {
  const cells = new Map<string, FacilityCell>();
  for (const f of list) {
    if (!f.geometry) continue;
    const [lon, lat] = f.geometry.coordinates;
    const h3 = latLngToCell(lat, lon, res);
    const c = cells.get(h3) ?? { h3, count: 0, active: 0 };
    c.count += 1;
    if (!isInactive(f)) c.active += 1;
    cells.set(h3, c);
  }
  return [...cells.values()];
}
