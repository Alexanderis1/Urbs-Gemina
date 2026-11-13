import { DATA_KINDS, type DataKind, type Envelope } from "./types";

function fail(msg: string): never {
  throw new Error(`Invalid tool envelope: ${msg}`);
}

const isObj = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

/** Validates a tool response. A response without a run id is refused: no number without a run id. */
export function parseEnvelope(raw: unknown): Envelope {
  if (!isObj(raw)) fail("not an object");
  if (typeof raw.run_id !== "string" || raw.run_id.length === 0) fail("missing run_id");
  if (typeof raw.tool !== "string") fail("missing tool");
  if (!isObj(raw.inputs)) fail("missing inputs");
  if (!isObj(raw.result)) fail("missing result");
  if (!isObj(raw.data_kinds)) fail("missing data_kinds");
  for (const [layer, kind] of Object.entries(raw.data_kinds)) {
    if (!DATA_KINDS.includes(kind as DataKind)) fail(`unknown data kind "${String(kind)}" for ${layer}`);
  }
  if (!Array.isArray(raw.sources)) fail("missing sources");
  for (const s of raw.sources) {
    if (!isObj(s) || typeof s.id !== "string" || typeof s.retrieved_at !== "string") fail("bad source entry");
  }
  if (typeof raw.synthetic !== "boolean") fail("missing synthetic flag");
  if (!Array.isArray(raw.warnings)) fail("missing warnings");
  return raw as unknown as Envelope;
}

const RANK: Record<DataKind, number> = { real: 0, estimated: 1, simulated: 2 };

/** The badge for a whole response: SIMULATED if anything synthetic is in it, else the weakest layer kind. */
export function envelopeBadge(env: Envelope): DataKind {
  if (env.synthetic) return "simulated";
  let worst: DataKind = "real";
  for (const k of Object.values(env.data_kinds)) if (RANK[k] > RANK[worst]) worst = k;
  return worst;
}

export function layerBadges(env: Envelope): [string, DataKind][] {
  return Object.entries(env.data_kinds).sort(([a], [b]) => a.localeCompare(b));
}
