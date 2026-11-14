// How data layers sit on the 3D city ("digital twin") so an operator always sees where things are:
// base map < 3D buildings < data < street and place names.

/** deck.gl draw settings for data shown over the 3D city: a building never hides it. */
export const OVER_TWIN = { depthCompare: "always", depthWriteEnabled: false } as const;

/** The building tiles start at this zoom (twin/model, buildings.pmtiles). Below it only the base map is drawn. */
export const TWIN_MIN_ZOOM = 12;

/** Opening zoom for whole-city screens: the closest view of Rome that still shows the 3D buildings. */
export const TWIN_START_ZOOM = 12.3;

export function twinVisible(zoom: number): boolean {
  return zoom >= TWIN_MIN_ZOOM;
}

export interface StyleLayerRef {
  id: string;
  type: string;
}

/** Data goes just under the first name on the map, so street and place names stay readable on top of it. */
export function labelAnchor(layers: readonly StyleLayerRef[]): string | undefined {
  return layers.find((l) => l.type === "symbol")?.id;
}

/** Buildings go under the data already on the map (deck.gl layers are "custom"), otherwise under the names. */
export function buildingAnchor(layers: readonly StyleLayerRef[]): string | undefined {
  return layers.find((l) => l.type === "custom")?.id ?? labelAnchor(layers);
}
