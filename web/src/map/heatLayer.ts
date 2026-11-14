// The smooth heatmap of src/lib/heatRaster.ts as a deck.gl layer: one picture laid on the city.
import { BitmapLayer } from "@deck.gl/layers";
import type { HeatRaster } from "@/lib/heatRaster";

/** Turns the pixels into a canvas once; null where there is no canvas (tests) or nothing to draw. */
export function rasterCanvas(r: HeatRaster): HTMLCanvasElement | null {
  if (!r.width || !r.height || typeof document === "undefined") return null;
  const canvas = document.createElement("canvas");
  canvas.width = r.width;
  canvas.height = r.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.putImageData(new ImageData(new Uint8ClampedArray(r.pixels), r.width, r.height), 0, 0);
  return canvas;
}

/** Pickable, so the screen can show the value under the pointer with `raster.nearest(info.coordinate)`. */
export function heatLayer(id: string, raster: HeatRaster, canvas: HTMLCanvasElement | null): BitmapLayer | null {
  if (!canvas) return null;
  return new BitmapLayer({
    id,
    image: canvas,
    bounds: raster.bounds,
    pickable: true,
    // Linear smoothing between pixels: no visible steps when zooming in.
    textureParameters: { minFilter: "linear", magFilter: "linear" },
  });
}
