import { useEffect, useRef, useState } from "react";
import maplibregl, { type Map as MlMap, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { Protocol } from "pmtiles";
import { Building2 } from "lucide-react";
import { onMapAction } from "@/lib/mapbus";
import { buildingColor, type BuildingView } from "@/lib/buildingStyles";
import { MAP_PALETTE, type Theme } from "@/lib/theme";
import { useTheme } from "@/lib/useTheme";
import { texts, tr } from "@/lib/i18n";
import { buildingAnchor, labelAnchor, OVER_TWIN, TWIN_START_ZOOM, twinVisible } from "@/lib/twinOverlay";
import { zoomStep } from "@/lib/markers";

// Base maps: Positron for the light theme, Dark for the operations-room theme (both OpenFreeMap, no key).
const STYLE_URLS: Record<Theme, string> = {
  light: (import.meta.env.VITE_BASEMAP_STYLE as string | undefined) || "https://tiles.openfreemap.org/styles/positron",
  dark: (import.meta.env.VITE_BASEMAP_STYLE_DARK as string | undefined) || "https://tiles.openfreemap.org/styles/dark",
};
// Credit line for the tiles; change it together with the URL if the tile variant changes (e.g. OSM-only heights).
const G0_ATTRIBUTION =
  (import.meta.env.VITE_BUILDINGS_ATTRIBUTION as string | undefined) ||
  "Buildings © OpenStreetMap contributors / Overture (ODbL). Heights: GlobalBuildingAtlas, TUM (CC BY-NC 4.0, non-commercial); Copernicus Urban Atlas. Terrain: Copernicus DEM.";
// Public copy on Cloudflare R2 (byte ranges + CORS for Lovable domains and localhost 5173/8080/4173).
const G0_DEFAULT = "https://pub-92f3b81279724b93b2c580e6b7c1cb37.r2.dev/buildings.pmtiles";
const ZOOM_TEXT = texts({
  en: { zoomIn: "Zoom in to see the 3D buildings" },
  it: { zoomIn: "Ingrandisci per vedere gli edifici in 3D" },
});

const G0_ENV = import.meta.env.VITE_BUILDINGS_PMTILES_URL as string | undefined;
// Unset = the R2 copy. Set to "osm" to use the base map's OpenStreetMap buildings instead.
const TREES_ENV = import.meta.env.VITE_TREES_PMTILES_URL as string | undefined;
const TREES_DEFAULT = "https://pub-92f3b81279724b93b2c580e6b7c1cb37.r2.dev/trees.pmtiles";
const TREES_RAW = TREES_ENV === undefined || TREES_ENV === "" ? TREES_DEFAULT : TREES_ENV === "off" ? "" : TREES_ENV;
const TREES_PMTILES = TREES_RAW && typeof window !== "undefined" ? new URL(TREES_RAW, window.location.href).href : TREES_RAW;
const G0_RAW = G0_ENV === undefined || G0_ENV === "" ? G0_DEFAULT : G0_ENV === "osm" ? "" : G0_ENV;
// The pmtiles protocol needs an absolute URL; a relative one (e.g. /buildings.pmtiles) is resolved against the page.
const G0_PMTILES = G0_RAW && typeof window !== "undefined" ? new URL(G0_RAW, window.location.href).href : G0_RAW;

/** Where a screen wants the camera: a point with a zoom, or a box to frame (e.g. a flood footprint). */
export type MapFocus =
  | { lon: number; lat: number; zoom: number; pitch?: number }
  | { bounds: [[number, number], [number, number]]; pitch?: number };

export const ROME = { lat: 41.8986, lon: 12.4769 };

let protocolAdded = false;

/** Plain background used when the base-map server cannot be reached (offline demo, blocked network). */
const fallbackStyle = (theme: Theme): StyleSpecification => ({
  version: 8,
  sources: {},
  layers: [{ id: "background", type: "background", paint: { "background-color": MAP_PALETTE[theme].background } }],
});

async function loadStyle(theme: Theme): Promise<StyleSpecification> {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 4000);
    const res = await fetch(STYLE_URLS[theme], { signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) throw new Error(String(res.status));
    return (await res.json()) as StyleSpecification;
  } catch {
    console.warn("[urbs] base map unreachable, using plain background");
    return fallbackStyle(theme);
  }
}

/** G0 block model. Uses the WS2 PMTiles when configured, otherwise the base map's OSM buildings. */
function addBuildings(map: MlMap, theme: Theme) {
  const palette = MAP_PALETTE[theme];
  if (map.getLayer("g0-extrusion") || map.getLayer("osm-buildings-3d")) return;
  const style = map.getStyle() as StyleSpecification;
  // Under the data and under the names: base map < buildings < data < street and place names.
  const firstSymbol = buildingAnchor(style.layers);
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
          // Estimated heights (no measured source) are drawn a little lighter; other views via buildingView.
          "fill-extrusion-color": buildingColor("plain", theme),
          "fill-extrusion-height": ["coalesce", ["get", "height_m"], 9.6],
          "fill-extrusion-opacity": 0.9,
        },
      },
      firstSymbol,
    );
    if (TREES_PMTILES) {
      map.addSource("trees", { type: "vector", url: `pmtiles://${TREES_PMTILES}`, attribution: "Trees: Meta / WRI canopy height (CC BY 4.0)" });
      map.addLayer(
        {
          id: "trees-3d",
          type: "fill-extrusion",
          source: "trees",
          "source-layer": "trees",
          minzoom: 14,
          layout: { visibility: "none" },
          paint: {
            "fill-extrusion-color": palette.tree,
            "fill-extrusion-base": ["coalesce", ["get", "base_m"], 0],
            "fill-extrusion-height": ["coalesce", ["get", "height_m"], 8],
            "fill-extrusion-opacity": 0.75,
          },
        },
        firstSymbol,
      );
    }
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
        "fill-extrusion-color": palette.building,
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
  // Whole-city screens open at the widest view that still shows the 3D buildings.
  initialZoom = TWIN_START_ZOOM,
  pitch = 50,
  focus,
  buildingView = "plain",
  showTrees = false,
  onZoom,
  onZoomStep,
  onHover,
  onPick,
  zoomHint = true,
}: {
  layers: Layer[];
  /**
   * Optional: called on every click or tap with what was under it (object is undefined on empty map).
   * A click on an item belongs to the item and is not also passed to `onClick`, unless this returns false.
   */
  onPick?: (info: PickingInfo) => boolean | void;
  /** Called while zooming, each time the zoom passes a quarter step: 3D markers keep their size on screen with it. */
  onZoomStep?: (zoom: number) => void;
  /** Optional: called when the pointer moves over a pickable deck.gl item (object is undefined when over nothing). */
  onHover?: (info: PickingInfo) => void;
  buildingView?: BuildingView;
  showTrees?: boolean;
  /** Camera target set by the screen itself (local, not through the shared map-action bus). */
  focus?: MapFocus | null;
  onClick?: (lngLat: { lat: number; lon: number }) => void;
  /** Called with the zoom level after each zoom ends. */
  onZoom?: (zoom: number) => void;
  initialZoom?: number;
  pitch?: number;
  /** False on maps that are meant to show the whole city: no "zoom in to see the buildings" offer. */
  zoomHint?: boolean;
}) {
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const clickRef = useRef(onClick);
  clickRef.current = onClick;
  const zoomRef = useRef(onZoom);
  zoomRef.current = onZoom;
  const hoverRef = useRef(onHover);
  hoverRef.current = onHover;
  const pickRef = useRef(onPick);
  pickRef.current = onPick;
  const stepRef = useRef(onZoomStep);
  stepRef.current = onZoomStep;
  const { theme } = useTheme();
  const themeRef = useRef(theme);
  themeRef.current = theme;
  // The first name layer of the current base map: data is drawn just under it.
  const [nameLayer, setNameLayer] = useState<string | undefined>(undefined);
  // False when the view is too wide for the building tiles: the screen then offers one click back to them.
  const [twinShown, setTwinShown] = useState(true);

  useEffect(() => {
    if (!el.current) return;
    if (!protocolAdded) {
      maplibregl.addProtocol("pmtiles", new Protocol().tile);
      protocolAdded = true;
    }
    const map = new maplibregl.Map({
      container: el.current,
      style: fallbackStyle(themeRef.current),
      center: [ROME.lon, ROME.lat],
      zoom: initialZoom,
      pitch,
      bearing: -15,
      maxPitch: 75,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    const overlay = new MapboxOverlay({
      interleaved: true,
      layers: [],
      onHover: (info) => {
        if (!hoverRef.current) return;
        hoverRef.current(info);
        // Pointer cursor over something that has details, only on screens that show them.
        map.getCanvas().style.cursor = info.object ? "pointer" : "";
      },
    });
    map.addControl(overlay);
    // Start with the credits folded behind the (i) button so they do not cover the map legend; one click opens them.
    // MapLibre opens them as soon as the first source brings a credit line, so fold once right after that.
    const foldCredits = () => {
      const credits = el.current?.querySelector(".maplibregl-ctrl-attrib");
      if (!credits?.classList.contains("maplibregl-compact-show")) return;
      credits.classList.remove("maplibregl-compact-show");
      credits.removeAttribute("open");
      map.off("sourcedata", foldCredits);
    };
    map.on("sourcedata", foldCredits);
    map.on("click", (e) => {
      // A click or tap on a marker belongs to the marker (its card opens); it is not also a click on the map under it.
      // Asked here rather than remembered from a hover, because a touch screen has no hover.
      if (pickRef.current) {
        const info = overlay.pickObject({ x: e.point.x, y: e.point.y, radius: 4 });
        const taken = pickRef.current(info ?? ({ x: e.point.x, y: e.point.y, object: undefined, layer: null } as unknown as PickingInfo));
        if (info?.object && taken !== false) return;
      }
      clickRef.current?.({ lat: e.lngLat.lat, lon: e.lngLat.lng });
    });
    map.on("zoomend", () => zoomRef.current?.(map.getZoom()));
    let step = NaN;
    const checkTwin = () => {
      setTwinShown(twinVisible(map.getZoom()));
      const next = zoomStep(map.getZoom());
      if (next !== step) stepRef.current?.((step = next));
    };
    map.on("zoom", checkTwin);
    checkTwin();
    mapRef.current = map;
    if (import.meta.env.DEV) (window as unknown as { __urbsMap?: MlMap }).__urbsMap = map;
    overlayRef.current = overlay;
    const off = onMapAction((a) => {
      if (a.tool === "fly_to") map.flyTo({ center: [a.args.lon, a.args.lat], zoom: a.args.zoom ?? 16, pitch: 60 });
      if (a.tool === "show_radius") map.flyTo({ center: [a.args.lon, a.args.lat], zoom: 15.5, pitch: 50 });
    });
    return () => {
      off();
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
    };
  }, [initialZoom, pitch]);

  // Base map for the current theme. Runs on mount and again when the theme is switched (the camera stays put).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    let cancelled = false;
    void loadStyle(theme).then((style) => {
      if (cancelled || mapRef.current !== map) return;
      map.once("style.load", () => {
        addBuildings(map, theme);
        setNameLayer(labelAnchor(map.getStyle().layers));
      });
      // diff: false, so "style.load" always fires (a diff against an identical fallback style would not).
      map.setStyle(style, { diff: false });
    });
    return () => {
      cancelled = true;
    };
  }, [theme, initialZoom, pitch]);

  // Every data layer is drawn on top of the 3D city (a building never hides it) and under the names.
  useEffect(() => {
    overlayRef.current?.setProps({
      layers: layers.map((l) => l.clone({ beforeId: nameLayer, parameters: { ...OVER_TWIN, ...l.props.parameters } } as object)),
    });
  }, [layers, nameLayer]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      if (map.getLayer("g0-extrusion")) map.setPaintProperty("g0-extrusion", "fill-extrusion-color", buildingColor(buildingView, theme));
      if (map.getLayer("trees-3d")) map.setLayoutProperty("trees-3d", "visibility", showTrees ? "visible" : "none");
    };
    apply();
    map.on("styledata", apply);
    return () => {
      map.off("styledata", apply);
    };
  }, [buildingView, showTrees, theme]);

  useEffect(() => {
    const map = mapRef.current;
    if (!focus || !map) return;
    if ("bounds" in focus) map.fitBounds(focus.bounds, { padding: 60, maxZoom: 16, pitch: focus.pitch ?? 30, duration: 1200 });
    else map.flyTo({ center: [focus.lon, focus.lat], zoom: focus.zoom, pitch: focus.pitch ?? 55 });
  }, [focus]);

  return (
    <div className="relative h-full w-full">
      <div ref={el} className="h-full w-full" />
      {G0_PMTILES && zoomHint && !twinShown && (
        <button
          type="button"
          className="map-float absolute bottom-20 right-3 z-10 hidden animate-fade-in items-center gap-2 px-3 py-2 text-xs font-semibold text-link hover:underline md:flex"
          onClick={() => mapRef.current?.easeTo({ zoom: TWIN_START_ZOOM, duration: 600 })}
        >
          <Building2 className="h-4 w-4" aria-hidden="true" />
          {tr(ZOOM_TEXT).zoomIn}
        </button>
      )}
    </div>
  );
}
