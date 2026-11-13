# City model (WS2)

| Layer | What | Extent | Status |
|---|---|---|---|
| **G0** | LoD1 blocks: footprint + one height + ground level per building | Whole city | Built by `scripts/build_city_model.py` |
| G2 | LoD2 roofs from the free MASE LiDAR (1 m, 2008-2011) | About 16 km² along the Tiber | Planned |
| G1 | Gaussian-splat landmarks (appearance only, never used by simulations) | A few landmarks | Planned |

## G0 in one paragraph

Footprints come from Overture (mostly OpenStreetMap). Each building takes the first height it can find, in this order (set in `config/model.yaml`):

1. `osm_tag`: a height measured by OSM mappers (`real`)
2. `gba`: GlobalBuildingAtlas machine-learning height, with its standard deviation (`estimated`, **CC BY-NC 4.0, non-commercial**)
3. `raster`: Copernicus Urban Atlas Building Height 2012 class midpoint (`estimated`)
4. `floors`: floor count x 3.2 m (`estimated`)
5. `default`: 9 m (`estimated`, flagged in the honesty panel)

Ground level comes from the Copernicus GLO-30 surface model (low percentile on a ring around the building, because a surface model includes roofs). TINITALY 10 m will replace it.

## Build

```bash
pip install -e .[model]
python scripts/build_city_model.py                                   # whole city
python scripts/build_city_model.py --bbox 12.46 41.88 12.50 41.91    # test box
```

Outputs in `data/processed/model/` (git-ignored):

| File | Use |
|---|---|
| `buildings_lod1.parquet` | GeoParquet (WGS84) with every attribute, for tools and scenarios (WS4, WS6) |
| `buildings.pmtiles` | Vector tiles for the MapLibre viewer (WS8) |
| `height_check.md` | Validation report for the honesty panel |
| `build.json` | Same numbers as JSON, plus SHA-256 of every input and output |

## Publishing the tiles

`--upload` copies the outputs to any S3-compatible bucket (Cloudflare R2, AWS S3, MinIO), set only by environment variables:

```bash
export URBS_TILES_S3_ENDPOINT=https://<account>.r2.cloudflarestorage.com
export URBS_TILES_BUCKET=urbs-gemina URBS_TILES_PREFIX=model
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
python scripts/build_city_model.py --upload
```

The bucket needs public read and a CORS rule that allows `GET`/`HEAD` with the `Range` header, because the viewer reads PMTiles by byte ranges.

## Viewer handoff (WS8)

PMTiles source layer `buildings`, zoom 12-16 (overzoom above 16). Feature properties:

| Property | Meaning |
|---|---|
| `id` | Overture building id |
| `height_m` | Height above ground (m) |
| `height_sd_m` | One standard deviation of the height, when known (GBA only) |
| `height_source` | `osm_tag`, `gba`, `raster`, `floors` or `default` |
| `data_kind` | `real` or `estimated` |
| `ground_m`, `roof_m` | Ground and roof elevation above sea level (m) |
| `class` | Overture building class, when known |

MapLibre style sketch:

```js
map.addSource("buildings", { type: "vector", url: "pmtiles://<host>/buildings.pmtiles" });
map.addLayer({
  id: "buildings-3d", type: "fill-extrusion", source: "buildings", "source-layer": "buildings",
  paint: {
    "fill-extrusion-height": ["get", "height_m"],
    "fill-extrusion-color": ["match", ["get", "data_kind"], "real", "#d9d4c7", "#c9c2b0"],
    "fill-extrusion-opacity": 0.9
  }
});
```

Attribution to show with the layer: "Buildings © OpenStreetMap contributors / Overture Maps (ODbL). Heights: GlobalBuildingAtlas, TUM (CC BY-NC 4.0, non-commercial); Copernicus Urban Atlas. Terrain: Copernicus DEM."
