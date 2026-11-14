// 3D markers on the city model: a column rising from the exact spot, a round badge with a glyph on top
// (places) or the value written on top (readings), a footprint on the ground, and a ring around the chosen one.
// Columns are real 3D: buildings in front hide them, they hide buildings behind. Badges and values always show.
// Reasoning: docs/design-system.md, decision 28.
import { ColumnLayer, IconLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { columnPx, columnScale, isDense, MARKER, metersPerPixel } from "@/lib/markers";
import type { MapPalette } from "@/lib/theme";
import { glyphUrl, type Glyph } from "./markerGlyphs";

type Rgb = [number, number, number];

export interface Marker<T = unknown> {
  id: string;
  position: [number, number];
  color: Rgb;
  /** 0..1 for a reading (column height follows the value); null for a place (one height for all). */
  level: number | null;
  /** Glyph on the badge. Left out for readings that carry `text` instead. */
  glyph?: Glyph;
  /** Short text on top of the column, e.g. the value. */
  text?: string;
  /** Simulated items get the simulated outline colour. */
  synthetic?: boolean;
  data: T;
}

export interface MarkerOptions {
  /** Prefix of the layer ids: screens tell their marker sets apart with it. */
  id: string;
  zoom: number;
  palette: MapPalette;
  selectedId?: string | null;
  hoveredId?: string | null;
  /** Force slim columns without badges (default: by the number of markers). */
  dense?: boolean;
}

/** Real 3D for the columns (the shared default for data is "always on top"). */
const SOLID = { depthCompare: "less-equal", depthWriteEnabled: true, cullMode: "back" } as const;

const hexRgb = (hex: string): Rgb => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as Rgb;

/** The marker a hover or click landed on, when it belongs to the marker set `id`. */
export function pickedMarker<T>(info: PickingInfo, id: string): Marker<T> | null {
  return info.object && info.layer?.id.startsWith(`${id}-`) ? (info.object as Marker<T>) : null;
}

export function markerLayers<T>(markers: Marker<T>[], opts: MarkerOptions): Layer[] {
  if (!markers.length) return [];
  const { id, palette } = opts;
  const scale = columnScale(opts.zoom);
  const dense = opts.dense ?? isDense(markers.length);
  const radius = dense ? MARKER.denseRadiusPx : MARKER.radiusPx;
  const surface = hexRgb(palette.surface);
  const ink = hexRgb(palette.text.ink);
  const top = (m: Marker<T>): [number, number, number] => [m.position[0], m.position[1], columnPx(m.level) * scale];
  const focusIds = [opts.selectedId, opts.hoveredId].filter((x): x is string => !!x);
  const focus = focusIds.length ? markers.filter((m) => focusIds.includes(m.id)) : [];
  // Many markers: only the one under the pointer and the chosen one carry a badge.
  const badged = dense ? focus : markers;
  const withGlyph = badged.filter((m) => m.glyph);
  const withText = badged.filter((m) => m.text && !m.glyph);
  const selected = markers.filter((m) => m.id === opts.selectedId);
  const highlight: [number, number, number, number] = [...palette.accent, 255];

  return [
    // Footprint: where exactly the thing is, readable even when a building hides the foot of the column.
    new ScatterplotLayer<Marker<T>>({
      id: `${id}-base`,
      data: markers,
      getPosition: (m) => m.position,
      getRadius: radius + 4,
      radiusUnits: "pixels",
      getFillColor: (m) => [...m.color, 70],
      stroked: true,
      getLineColor: (m) => (m.synthetic ? [...palette.simulated, 255] : [...m.color, 230]),
      getLineWidth: (m) => (m.synthetic ? 2 : 1.5),
      lineWidthUnits: "pixels",
      pickable: true,
      updateTriggers: { getFillColor: [palette], getLineColor: [palette] },
    }),
    new ScatterplotLayer<Marker<T>>({
      id: `${id}-selected`,
      data: selected,
      getPosition: (m) => m.position,
      getRadius: radius + 13,
      radiusUnits: "pixels",
      filled: true,
      getFillColor: [...palette.accent, 40],
      stroked: true,
      getLineColor: highlight,
      getLineWidth: 2.5,
      lineWidthUnits: "pixels",
    }),
    new ColumnLayer<Marker<T>>({
      id: `${id}-column`,
      data: markers,
      getPosition: (m) => m.position,
      diskResolution: dense ? 6 : 16,
      // In metres, sized from the zoom, so the column keeps the same width on screen.
      radius: radius * metersPerPixel(opts.zoom),
      extruded: true,
      getElevation: (m) => columnPx(m.level),
      elevationScale: scale,
      getFillColor: (m) => (m.id === opts.selectedId ? highlight : [...m.color, 255]),
      material: { ambient: 0.55, diffuse: 0.6, shininess: 24, specularColor: [60, 64, 70] },
      pickable: true,
      autoHighlight: true,
      highlightColor: highlight,
      parameters: SOLID,
      transitions: { elevationScale: 200, radius: 200 },
      updateTriggers: { getFillColor: [opts.selectedId, palette] },
    }),
    // Round badge at the top of the column, always facing the viewer.
    new ScatterplotLayer<Marker<T>>({
      id: `${id}-badge`,
      data: withGlyph,
      getPosition: top,
      billboard: true,
      getRadius: (m) => (focusIds.includes(m.id) ? MARKER.badgePx + 3 : MARKER.badgePx),
      radiusUnits: "pixels",
      getFillColor: (m) => (m.id === opts.selectedId ? highlight : [...m.color, 255]),
      stroked: true,
      getLineColor: (m) => (m.synthetic ? [...palette.simulated, 255] : [...surface, 255]),
      getLineWidth: 2,
      lineWidthUnits: "pixels",
      pickable: true,
      updateTriggers: {
        getPosition: [scale],
        getRadius: [opts.selectedId, opts.hoveredId],
        getFillColor: [opts.selectedId, palette],
        getLineColor: [palette],
      },
    }),
    new IconLayer<Marker<T>>({
      id: `${id}-glyph`,
      data: withGlyph,
      getPosition: top,
      getIcon: (m) => ({ url: glyphUrl(m.glyph!), id: m.glyph!, width: 64, height: 64, mask: true }),
      getSize: (m) => (focusIds.includes(m.id) ? 18 : 14),
      sizeUnits: "pixels",
      getColor: [255, 255, 255, 255],
      updateTriggers: { getPosition: [scale], getSize: [opts.selectedId, opts.hoveredId] },
    }),
    new TextLayer<Marker<T>>({
      id: `${id}-text`,
      data: withText,
      getPosition: top,
      getText: (m) => m.text!,
      getSize: 12,
      getColor: [...ink, 255],
      getPixelOffset: [0, -12],
      fontFamily: '"Titillium Web", sans-serif',
      fontWeight: 600,
      background: true,
      getBackgroundColor: [...surface, 240],
      getBorderColor: (m) => [...m.color, 255],
      getBorderWidth: 1.5,
      backgroundPadding: [5, 2],
      pickable: true,
      updateTriggers: { getPosition: [scale], getColor: [palette], getBackgroundColor: [palette], getBorderColor: [palette] },
    }),
  ];
}
