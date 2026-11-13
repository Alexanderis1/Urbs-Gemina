import { useEffect, useRef } from "react";
import maplibregl, { type Map as MlMap, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import type { Layer } from "@deck.gl/core";
import { Protocol } from "pmtiles";
import { onMapAction } from "@/lib/mapbus";

const STYLE_URL =
  (import.meta.env.VITE_BASEMAP_STYLE as string | undefined) || "https://tiles.openfreemap.org/styles/positron";
// Credit line for the tiles; change it together with the URL if the tile variant changes (e.g. OSM-only heights).
const G0_ATTRIBUTION =
  (import.meta.env.VITE_BUILDINGS_ATTRIBUTION as string | undefined) ||
  "Buildings © OpenStreetMap contributors / Overture (ODbL). Heights: GlobalBuildingAtlas, TUM (CC BY-NC 4.0, non-commercial); Copernicus Urban Atlas. Terrain: Copernicus DEM.";
const G0_RAW = (import.meta.env.VITE_BUILDINGS_PMTILES_URL as string | undefined) ?? "";
// The pmtiles protocol needs an absolute URL; a relative one (e.g. /buildings.pmtiles) is resolved against the page.
const G0_PMTILES = G0_RAW && typeof window !== "undefined" ? new URL(G0_RAW, window.location.href).href : G0_RAW;

export const ROME = { lat: 41.8986, lon: 12.4769 };

let protocolAdded = false;

/** Plain background used when the base-map server cannot be reached (offline demo, blocked network). */
const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "background", type: "background", paint: { "background-color": "#efe9df" } }],
};

async function loadStyle(): Promise<string | StyleSpecification> {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 4000);
    const res = await fetch(STYLE_URL, { signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) throw new Error(String(res.status));
    return (await res.json()) as StyleSpecification;
  } catch {
    console.warn("[urbs] base map unreachable, using plain background");
    return FALLBACK_STYLE;
  }
}

/** G0 block model. Uses the WS2 PMTiles when configured, otherwise the base map's OSM buildings. */
function addBuildings(map: MlMap) {
  if (map.getLayer("g0-extrusion") || map.getLayer("osm-buildings-3d")) return;
  const style = map.getStyle() as StyleSpecification;
  const firstSymbol = style.layers.find((l) => l.type === "symbol")?.id;
  if (G0_PMTILES) {
    // WS2 G0 block model (twin/model/README.md): source-layer "buildings", height in "height_m", zoom 12-16.
    map.addSource("g0", {
      type: "vector",
      url: `pmtiles://${G0_PMTILES}`,
      attribution: G0_ATTRIBUTION,
    });
    map.addLayer(
      {
        id: "g0-extrusion",
        type: "fill-extrusion",
        source: "g0",
        "source-layer": "buildings",
        paint: {
          // Estimated heights (no measured source) are drawn a little lighter.
          "fill-extrusion-color": ["match", ["get", "data_kind"], "real", "#cfc6b8", "#e3ddd3"],
          "fill-extrusion-height": ["coalesce", ["get", "height_m"], 9.6],
          "fill-extrusion-opacity": 0.9,
        },
      },
      firstSymbol,
    );
    return;
  }
  const src = Object.entries(style.sources).find(([, s]) => s.type === "vector")?.[0];
  if (!src) return;
  map.addLayer(
    {
      id: "osm-buildings-3d",
      type: "fill-extrusion",
      source: src,
      "source-layer": "building",
      minzoom: 13,
      paint: {
        "fill-extrusion-color": "#d6cfc4",
        "fill-extrusion-height": ["coalesce", ["get", "render_height"], 9.6],
        "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
        "fill-extrusion-opacity": 0.85,
      },
    },
    firstSymbol,
  );
}

export function CityMap({
  layers,
  onClick,
  initialZoom = 11,
  pitch = 50,
  focus,
}: {
  layers: Layer[];
  /** Camera target set by the screen itself (local, not through the shared map-action bus). */
  focus?: { lon: number; lat: number; zoom: number } | null;
  onClick?: (lngLat: { lat: number; lon: number }) => void;
  initialZoom?: number;
  pitch?: number;
}) {
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const clickRef = useRef(onClick);
  clickRef.current = onClick;

  useEffect(() => {
    if (!el.current) return;
    if (!protocolAdded) {
      maplibregl.addProtocol("pmtiles", new Protocol().tile);
      protocolAdded = true;
    }
    const map = new maplibregl.Map({
      container: el.current,
      style: FALLBACK_STYLE,
      center: [ROME.lon, ROME.lat],
      zoom: initialZoom,
      pitch,
      bearing: -15,
      maxPitch: 75,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    const overlay = new MapboxOverlay({ interleaved: true, layers: [] });
    map.addControl(overlay);
    let cancelled = false;
    void loadStyle().then((style) => {
      if (cancelled) return;
      if (style === FALLBACK_STYLE) {
        if (map.isStyleLoaded()) addBuildings(map);
        else map.once("load", () => addBuildings(map));
        return;
      }
      map.once("style.load", () => addBuildings(map));
      map.setStyle(style);
    });
    map.on("click", (e) => clickRef.current?.({ lat: e.lngLat.lat, lon: e.lngLat.lng }));
    mapRef.current = map;
    if (import.meta.env.DEV) (window as unknown as { __urbsMap?: MlMap }).__urbsMap = map;
    overlayRef.current = overlay;
    const off = onMapAction((a) => {
      if (a.tool === "fly_to") map.flyTo({ center: [a.args.lon, a.args.lat], zoom: a.args.zoom ?? 16, pitch: 60 });
      if (a.tool === "show_radius") map.flyTo({ center: [a.args.lon, a.args.lat], zoom: 15.5, pitch: 50 });
    });
    return () => {
      cancelled = true;
      off();
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
    };
  }, [initialZoom, pitch]);

  useEffect(() => {
    overlayRef.current?.setProps({ layers });
  }, [layers]);

  useEffect(() => {
    if (focus) mapRef.current?.flyTo({ center: [focus.lon, focus.lat], zoom: focus.zoom, pitch: 55 });
  }, [focus]);

  return <div ref={el} className="h-full w-full" />;
}
