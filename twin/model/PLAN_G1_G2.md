# City model detail layers: plan for G2 (LiDAR roofs) and G1 (splat landmarks)

Ordered steps with go/no-go gates. Each layer plugs into the same frame as G0 (WGS84 for the viewer, UTM 33N `EPSG:32633` for geometry work). Simulations use G0 and G2, never splats.

## G2: LoD2 roofs from the MASE LiDAR

Data: MASE "Download Banca Dati PST", 1 m DSM First, DSM Last and DTM, CC BY 4.0, flown 2008-2011, about 16 km² along the Tiber in the centre. Cells are 0.01° GeoTIFFs (EPSG:4326, orthometric heights).

1. **Get the tiles.** Manual download from the web app (draw the Tiber area, DSM First + DTM) or automatic once `gis.platform.sim.mase.gov.it` and `x2030-gis-polygon-downloader.platform.sim.mase.gov.it` are reachable. Store under `data/raw/mase_lidar/`.
   *Gate G2a*: DSM and DTM cover the centre box and line up with G0 footprints (median offset under 2 m). No-go: keep LoD1 there.
2. **Normalised surface (nDSM = DSM − DTM)** reprojected to UTM 33N at 0.5 m.
3. **Score G0 against LiDAR.** Per footprint: 90th percentile of nDSM = LiDAR height. Report bias, mean error and share within 3 m for each height source (osm_tag, gba, raster, floors). This becomes the strongest row of the height check.
   *Gate G2b*: LiDAR heights exist for most footprints in the covered area. No-go: report coverage only.
4. **LiDAR heights replace G0 heights** inside the coverage (`height_source = lidar`, `data_kind = real`, survey date shown).
5. **Roof shapes (LoD2).** Per footprint, fit roof planes on nDSM points (RANSAC, minimum plane area set in config), build a closed mesh: walls from the footprint, roof from the planes; fall back to a flat roof at the 90th percentile when the fit residual is too high.
   *Gate G2c*: median plane residual under 0.5 m on a sample of 200 buildings. No-go: ship "LiDAR flat roofs" (step 4 only).
6. **Tiles.** Export glTF per tile and build 3D Tiles (`tileset.json`) for deck.gl `Tile3DLayer` (WS8 way A), same origin as G0.

## G1: Gaussian-splat landmarks

Data: MegaScenes scenes (Wikimedia Commons photos with COLMAP camera poses). Candidate landmarks: Pantheon, Piazza Navona, Vittoriano, Roman Forum, St Peter's facade.

1. **Pick scenes.** For each landmark, read the MegaScenes scene and count registered images.
   *Gate G1a*: at least a few hundred registered images and a single connected model. No-go: drop that landmark.
2. **Clean inputs.** Remove images with heavy crowds or night shots where the scene has enough others; downscale to fit the GPU.
3. **Train.** 3D Gaussian splatting (gsplat / Nerfstudio splatfacto) on the RTX 4060 Ti 8 GB with downscaled images, or a rented A6000 48 GB for full resolution. Hold out a fixed share of images for scoring.
   *Gate G1b*: PSNR and SSIM on held-out photos reported; a scene that is visibly broken from the street viewpoint is dropped.
4. **Georeference.** Pick control points visible in both the splat and the AGEA orthophoto / G0 footprints; fit a similarity transform (scale, rotation, translation) into UTM 33N, keep unused points to measure the residual.
   *Gate G1c*: residual at unused control points small enough that the landmark sits on its G0 footprint (target under 2 m). No-go: show the splat in its own panel without placing it on the map.
5. **Export.** Compress (e.g. `.spz` / SOGS) for the web, record PSNR, SSIM and georeferencing residual in `build.json` for the honesty panel, label as "appearance only".
6. **Viewer.** Separate splat panel opened from the landmark on the map (WS8), since MapLibre has no splat layer.

## Open choices

| Choice | Options | Recommendation |
|---|---|---|
| LiDAR download | Manual ZIPs from the web app; allow the two MASE GIS hosts | Manual, it is one request per product |
| Splat training GPU | 4060 Ti 8 GB (free, downscaled); rented A6000 48 GB | Start on the 4060 Ti with one landmark, rent only if quality fails gate G1b |
| Landmarks | Pantheon, Navona, Vittoriano, Forum, St Peter's | Pantheon first: inside the LiDAR area, so G2 and G1 can be checked against each other |
