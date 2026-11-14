import type { PolygonGeometry } from "@/api/types";

const R = 6_371_008.8;
const rad = (d: number) => (d * Math.PI) / 180;
const deg = (r: number) => (r * 180) / Math.PI;

/** Great-circle distance in metres (display and geometry building only, never a reported figure). */
export function distanceM(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const dφ = rad(lat2 - lat1);
  const dλ = rad(lon2 - lon1);
  const a = Math.sin(dφ / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dλ / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

/** Circle around a point as a closed 64-vertex GeoJSON polygon, the hub's format for the context area. */
export function circlePolygon(lon: number, lat: number, radiusM: number, vertices = 64): PolygonGeometry {
  const φ1 = rad(lat);
  const λ1 = rad(lon);
  const δ = radiusM / R;
  const ring: number[][] = [];
  for (let i = 0; i < vertices; i++) {
    const θ = (2 * Math.PI * i) / vertices;
    const φ2 = Math.asin(Math.sin(φ1) * Math.cos(δ) + Math.cos(φ1) * Math.sin(δ) * Math.cos(θ));
    const λ2 = λ1 + Math.atan2(Math.sin(θ) * Math.sin(δ) * Math.cos(φ1), Math.cos(δ) - Math.sin(φ1) * Math.sin(φ2));
    ring.push([deg(λ2), deg(φ2)]);
  }
  ring.push([...ring[0]!]);
  return { type: "Polygon", coordinates: [ring] };
}

/** Bounding box [[west, south], [east, north]] of GeoJSON geometries. Used only to frame the map camera. */
export function boundsOf(geometries: { type?: string; coordinates?: unknown }[]): [[number, number], [number, number]] | null {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  const visit = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === "number" && typeof c[1] === "number") {
      w = Math.min(w, c[0]); e = Math.max(e, c[0]); s = Math.min(s, c[1]); n = Math.max(n, c[1]);
    } else if (Array.isArray(c)) c.forEach(visit);
  };
  for (const g of geometries) visit(g.coordinates);
  return Number.isFinite(w) ? [[w, s], [e, n]] : null;
}
