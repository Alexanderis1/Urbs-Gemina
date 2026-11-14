// A layer drawn along the streets instead of as patches (Alessandro, 14 Nov 2026): the value of the twin's cells
// is blended between neighbouring cells and painted on short pieces of each street, so the colour changes
// smoothly along the road. The streets are the main roads of Rome from Overture Maps (ODbL), a static file
// built by scripts/build_web_roads.py. Pure helpers; the drawing is in components/CitizenMap.tsx.
// Reasoning: docs/design-system.md, decision 33.
import { getHexagonEdgeLengthAvg, getResolution, gridDisk, latLngToCell, UNITS } from "h3-js";
import type { HeatCell } from "@/lib/here";

/** The road file: class names once, then each road as [class index, lon, lat, lon, lat, …]. */
export interface RoadNet {
  classes: string[];
  roads: [number, number[]][];
}

export interface RoadPiece {
  path: [number, number][];
  cls: string;
  /** 0..1 on the colour scale of the layer. */
  t: number;
  /** 0..1: how much the value rests on readings rather than on the model alone (0 = drawn neutral). */
  a: number;
  /** The nearest cell of the layer: what the card under the pointer shows. */
  cell: HeatCell;
}

const M_PER_DEG = 111_320;
/** Metres per degree of longitude at Rome. Basis: cos(41.9°) x 111.32 km. */
const M_PER_DEG_LON = M_PER_DEG * Math.cos((41.9 * Math.PI) / 180);
const metres = (lon1: number, lat1: number, lon2: number, lat2: number) => Math.hypot((lon2 - lon1) * M_PER_DEG_LON, (lat2 - lat1) * M_PER_DEG);

export type Field = (lon: number, lat: number) => { t: number; a: number; cell: HeatCell } | null;

/**
 * How much a cell rests on readings: 1 when its range is narrow, 0 when it is as wide as the value itself
 * (the model's starting map with no sensor nearby). Basis: on the live road speed layer (14 Nov 2026, 3,613
 * cells) cells near the simulated loops and buses have a range of 0.3-0.8 x the value; cells with only the
 * starting map 1.3-1.9 x. Between 0.8 and 1.2 the colour fades.
 */
export function certainty(c: HeatCell): number {
  if (c.low === undefined || c.high === undefined || !c.value) return 1;
  const width = (c.high - c.low) / Math.abs(c.value);
  return Math.max(0, Math.min(1, (1.2 - width) / 0.4));
}

/**
 * The layer as a smooth surface: at any point, the scores of the cell it falls in and of the six cells around it,
 * weighted by closeness. `score` puts a cell on the 0..1 colour scale. Cells need their grid id (`h3`).
 */
export function fieldOnCells(cells: HeatCell[], score: (c: HeatCell) => number, sure?: (c: HeatCell) => number): Field {
  const known = new Map<string, { cell: HeatCell; t: number; a: number }>();
  for (const c of cells) if (c.h3) known.set(c.h3, { cell: c, t: score(c), a: sure ? sure(c) : 1 });
  const first = cells.find((c) => c.h3)?.h3;
  if (!first) return () => null;
  const resolution = getResolution(first);
  // Distance between the centres of neighbouring cells (edge x √3): a cell's weight fades to nothing at the next centre.
  const reach = getHexagonEdgeLengthAvg(resolution, UNITS.m) * Math.sqrt(3) * 1.05;
  const around = new Map<string, { cell: HeatCell; t: number; a: number }[]>();
  return (lon, lat) => {
    const id = latLngToCell(lat, lon, resolution);
    let near = around.get(id);
    if (!near) {
      near = gridDisk(id, 1).flatMap((n) => known.get(n) ?? []);
      around.set(id, near);
    }
    if (!near.length) return null;
    let sum = 0;
    let sumA = 0;
    let weights = 0;
    let best = near[0]!;
    let bestD = Infinity;
    for (const n of near) {
      const d = metres(lon, lat, n.cell.lon, n.cell.lat);
      // Full weight at a cell's centre, none at the next centre: an even gradient from one cell to the next.
      const w = Math.max(1e-6, 1 - d / reach);
      sum += n.t * w;
      sumA += n.a * w;
      weights += w;
      if (d < bestD) {
        bestD = d;
        best = n;
      }
    }
    return { t: sum / weights, a: sumA / weights, cell: best.cell };
  };
}

/** Length of one piece of street. Basis: short enough that the colour steps between pieces are not seen at city zoom. */
export const PIECE_M = 120;

/** Cuts every road into pieces of about `pieceM` metres and gives each the value of the layer at its middle. */
export function roadPieces(net: RoadNet, at: Field, pieceM = PIECE_M): RoadPiece[] {
  const out: RoadPiece[] = [];
  for (const [classIndex, flat] of net.roads) {
    const cls = net.classes[classIndex] ?? "";
    let path: [number, number][] = [[flat[0]!, flat[1]!]];
    let length = 0;
    const close = () => {
      if (path.length < 2) return;
      const a = path[0]!;
      const b = path.at(-1)!;
      const mid = path[Math.floor(path.length / 2)]!;
      const [lon, lat] = path.length > 2 ? mid : [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      const v = at(lon, lat);
      if (v) out.push({ path, cls, t: v.t, a: v.a, cell: v.cell });
      path = [b];
      length = 0;
    };
    for (let i = 2; i + 1 < flat.length; i += 2) {
      const from = path.at(-1)!;
      const to: [number, number] = [flat[i]!, flat[i + 1]!];
      const d = metres(from[0], from[1], to[0], to[1]);
      // A long straight stretch is cut too, so it can change colour along the way.
      const parts = Math.max(1, Math.ceil(d / pieceM));
      for (let k = 1; k <= parts; k++) {
        const f = k / parts;
        path.push(k === parts ? to : [from[0] + (to[0] - from[0]) * f, from[1] + (to[1] - from[1]) * f]);
        length += d / parts;
        // Cut stretches are a little under a full piece; three quarters is enough to close one.
        if (length >= pieceM * 0.75) close();
      }
    }
    close();
  }
  return out;
}

/** Line width on screen at city zoom, by road class (Overture class names). Basis: assumption, the usual hierarchy of road maps. */
const WIDTH_PX: Record<string, number> = { motorway: 4.5, trunk: 4, primary: 3.2, secondary: 2.4, tertiary: 1.8 };
const OTHER_WIDTH_PX = 1.4;
/** Zoom at which the widths above apply; each zoom level in adds a quarter. */
const WIDTH_ZOOM = 10.5;

export function roadWidthPx(cls: string, zoom: number): number {
  const grow = Math.max(0.8, Math.min(3, 1 + (zoom - WIDTH_ZOOM) * 0.25));
  return (WIDTH_PX[cls] ?? OTHER_WIDTH_PX) * grow;
}

let loading: Promise<RoadNet | null> | null = null;

/** The main roads of Rome, fetched once. Null when the file cannot be read: the screen then draws the cells. */
export function loadRoads(): Promise<RoadNet | null> {
  loading ??= fetch(`${import.meta.env.BASE_URL}roads-rome.json`)
    .then((r) => (r.ok ? (r.json() as Promise<RoadNet>) : null))
    .then((net) => (net && Array.isArray(net.roads) && Array.isArray(net.classes) ? net : null))
    .catch(() => null);
  return loading;
}
