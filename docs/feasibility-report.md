# Build a narrow, probabilistic antenna twin of Rome

How to read the scores: **C=NN** is a confidence score from 1 to 100. **[src]** means a linked source supports the claim. **[bg]** means background knowledge that was not re-checked this session. **[inf]** means an inference or judgement. Claims with no tag are linked inline.

---

## Bottom line

**Verdict: the full idea is not feasible in ~20 hours (C=90).** A digital twin of Rome built from satellite and LEO imagery, public webcams and every public sensor is too much for one hackathon. Rebuilding 3D from satellites needs paid very-high-resolution imagery. Open, legally reusable webcams barely exist. IRIDE data is closed to you.

**A narrower version is feasible (C=75) [inf]:** an open 3D map of Rome, focused on Challenge 02, with a **probabilistic "belief grid"**. Each grid cell stores a mean value and an uncertainty for EMF (and, as a stretch, air quality). An **AI agent** runs the 300 m context check and writes a cited report.

| Cut | Keep | Stretch (only after the demo works) |
|---|---|---|
| Rebuilding 3D from satellites | Open 3D buildings (Overture/OSM) | Air-quality layer with uncertainty |
| IRIDE, any very-high-resolution satellite data | Antenna layer + 300 m context tool | ElevenLabs voice agent |
| Webcam scraping or storage | EMF belief grid (physics + measurements) | Thesis demo: WildTrack replay or 2 hand-calibrated webcams |
| City-scale Gaussian splats | Agent + Exa citations + tool trace | Google 3D Tiles as a backdrop only |

**Recommended pitch [inf]:** "A transparent, uncertainty-aware antenna twin for Rome: every number shows how sure it is, every rule is cited, and the code and data are open." It hits all three judging criteria. It also stands apart from [cartoradio.it](https://www.cartoradio.it/), which shows aggregated, anonymised estimates with no uncertainty.

---

## 1. Feasibility per component

| Component | Verdict | C |
|---|---|---|
| 3D base (open LoD1 buildings) | Yes. Use Overture/OSM footprints with heights and extrude them in deck.gl/MapLibre | 80 |
| 3D base (Google Photorealistic 3D Tiles) | Yes as a visual backdrop only. Needs billing, and analysis on the tiles is banned | 75 |
| Satellite / LEO imagery (Sentinel-2) | Yes as a 10 m layer. **Cannot** reconstruct buildings | 90 |
| IRIDE | **No.** Open to Italian public bodies only | 85 |
| Webcams + multi-view fusion | Only as a small, honest stretch. True multi-view needs overlapping calibrated cameras | 80 |
| Probabilistic sensor layer | Yes, as a GP/kriging belief grid with a physics prior | 80 |
| Antenna/EMF layer | Yes, but positions are partial and not official | 70 |
| Agents (permit check + data scout) | Yes, if the spatial maths stays in deterministic tools | 75 |

**Why satellites cannot give you 3D Rome.** Research methods that build 3D from satellites use 0.3–0.5 m WorldView-3 imagery with 10–30 views per 256 m tile. The best of them reach about 1.2–1.3 m DSM error on benchmark tiles ([EOGS++](https://arxiv.org/html/2511.16542v1)). Skyfall-GS adds AI-generated facades and needs a 48 GB GPU; its facades are invented, not measured ([Skyfall-GS](https://arxiv.org/html/2510.15869v2)). Sentinel-2 at 10 m cannot resolve single buildings in 3D [inf, C=90]. No free multi-view VHR image stack of Rome is known [bg, C=75].

**IRIDE.** IRIDE has 31 satellites in orbit, and its first image was of Rome at 2.66 m ([ESA](https://www.esa.int/Applications/Observing_the_Earth/IRIDE/Italy_s_Earth_monitoring_programme_reaches_new_milestone)). Its operational phase began on 1 July 2026, but free access goes first to Italian public bodies only, through the IRIDE Marketplace ([Startmag](https://en.startmag.it/spazio-e-difesa-2/iride-becomes-operational-satellite-data-and-geospatial-services-from-asi-launched/)). Mention it in the pitch as "future input", not as data you use.

**City-scale splats.** CityGaussianV2 needs 8×A100 and more than 4,000 images per scene ([arXiv](https://arxiv.org/html/2411.00771v2)). Not realistic here (C=90).

---

## 2. Literature map: research vs what industry uses

| Task | Research (2025–26) | What industry uses today |
|---|---|---|
| City 3D base | EOGS++, Skyfall-GS, CityGaussianV2 | Google 3D Tiles in Cesium/deck.gl; open LoD1 extrusions ([Google policies](https://developers.google.com/maps/documentation/tile/policies), [Overture](https://docs.overturemaps.org/guides/buildings)) |
| Global building heights | [GlobalBuildingAtlas](https://un-spider.org/news-and-events/news/globalbuildingatlas-open-global-3d-buildings-data-digital-twins-and-disaster): 3 m heights, RMSE 1.5–8.9 m, imagery from ~2019 | Overture/OSM heights, official building databases |
| Few-photo 3D | Feed-forward models: VGGT-Ω ([arXiv](https://arxiv.org/abs/2605.15195)), MapAnything ([arXiv](https://arxiv.org/pdf/2509.13414v3)); tourist photos: [WildGaussians](https://arxiv.org/html/2407.08447v2) | Cesium ion photo-to-splat service ([RadianceFields](https://radiancefields.com/cesium-adds-hierarchical-lod-for-gaussian-splats-to-3d-tiles-cesiumjs-and-cesium-for-unreal)) |
| Multi-view detection | MVDet → TrackTacular → SCFusion; WildTrack MODA 93.6 ([arXiv](https://arxiv.org/pdf/2509.08421)) | One homography per camera + detector + tracker ([TrafficLab-3D](https://yuk068.github.io//2026/02/20/traffilclab-3d-overview), NVIDIA [VSS calibration](https://docs.nvidia.com/vss/3.0.0/smartcity-docs/3.0.0/Calibration.html), C=60) |
| Camera → map pose | VIRD: 1.55 m on VIGOR ([arXiv](https://arxiv.org/html/2603.12918)); trained on car-mounted cameras, so it will likely fail on rooftop webcams [inf, C=75] | Hand-clicked landmark points + RANSAC |
| Cameras as sensors | — | FAA webcams' visibility fed into a Bayesian 2DVar analysis with a per-camera error variance ([Carley et al.](https://www.cambridge.org/core/product/3303F8BEC7EB9BDCF7D412FF11F238D9/core-reader)) |
| Probabilistic twin | Twin as a probabilistic graphical model with prior → posterior updates ([Kapteyn et al.](https://www.nature.com/articles/s43588-021-00069-0)) | Universal kriging with model drift; Barcelona NO2 RMSE −48% ([Criado et al.](https://gmd.copernicus.org/articles/16/2193/2023/)) |
| EMF mapping | ExposNet CNN, RMSE ~0.23–0.27 V/m ([arXiv](https://arxiv.org/pdf/2503.02966)); kNN beats XGBoost on 19k Catalan points ([Electronics 2025](https://mdpi-res.com/d_attachment/electronics/electronics-14-04766/article_deploy/electronics-14-04766.pdf)) | Grid sum of standard formulas per source (Cartoradio IT, 100 m cells, [SmartWorld](https://www.smartworld.it/news/cartoradio-mappa-campi-elettromagnetici-italia-gratis.html)); CEI 211-10 ([MIMIT FAQ](https://www.mise.gov.it/images/stories/documenti/FAQ_2024_campi_elettromagnetici_CCE.pdf)) |
| Ray tracing | [Sionna RT](https://nvlabs.github.io/sionna/examples/Sionna_Ray_Tracing_Coverage_Map.html) + [Geo2SigMap](https://github.com/functions-lab/geo2sigmap) | Use on 1–2 demo cells at most; needs a GPU [inf] |
| LLM geo-agents | [GeoBenchX](https://arxiv.org/html/2503.18129v2): no model solved more than ~half the tasks, and models were bad at refusing; [CityLLM](https://www.alphaxiv.org/abs/2607.14542.md): agent → SQL/Cypher on a 3D city model | Tool-calling agent over PostGIS/DuckDB with the tool trace shown |
| Zero-shot vision | [SAM 3](https://www.emergentmind.com/papers/2511.16719) text-prompted segmentation; cell-tower detection AP50 81.2 on Maxar imagery in Africa ([arXiv](https://arxiv.org/abs/2311.07840)) | COCO detectors (YOLO) for counts [bg, C=80] |

**Key lesson [inf, C=80]:** industry does not rebuild 3D cities live. It streams a ready-made 3D base, fuses sensors on a shared grid, and shows uncertainty as a separate layer. That is the right scope for you.

---

## 3. Rome data: what works today vs what does not

### Works today

All verified live on 13 Nov 2026 unless noted.

| Data | Source | Note |
|---|---|---|
| Sentinel-2 (10 m) | [CDSE STAC](https://stac.dataspace.copernicus.eu/v1/) | Scene from 10 Nov was 95% cloud; filter by cloud cover. Free account needed to download |
| Orthophoto (AGEA 2023) | [Lazio WMS](https://geoportale.regione.lazio.it/geoserver/ows?service=WMS&request=GetCapabilities) | GetMap returned an image. Per-layer licence unconfirmed (C=60) |
| DEM 10 m | [TINITALY](https://tinitaly.pi.ingv.it/) | Licence CC BY [bg, C=75] |
| 3D buildings | [Overture](https://docs.overturemaps.org/guides/buildings) (ODbL, release 2026-10-21) + [GlobalBuildingAtlas](https://github.com/zhu-xlab/GlobalBuildingAtlas) | Height completeness for Rome unknown (C=40) |
| Air quality (model) | [Open-Meteo AQ](https://air-quality-api.open-meteo.com/v1/air-quality?latitude=41.9&longitude=12.5&current=pm10,pm2_5,european_aqi) | Live, no key. Model values, not measurements |
| Air quality (low-cost sensors) | [Sensor.Community](https://data.sensor.community/airrohr/v1/filter/box=41.99,12.35,41.78,12.62) | Only 10 sensors in the Rome box |
| ARPA station metadata | [dati.lazio.it CKAN](https://dati.lazio.it/api/3/action/package_search?q=aria) | CC BY 4.0. Station lists and annual files only |
| Transport (GTFS + realtime) | [Roma Mobilità](https://romamobilita.it/it/tecnologie/open-data) | Licence not checked (C=50) |
| Earthquakes | [INGV FDSN](https://webservices.ingv.it/fdsnws/event/1/query?minlat=41.5&maxlat=42.3&minlon=12.0&maxlon=13.0&limit=2&format=text) | CC BY [bg, C=80] |
| Street photos | [Panoramax](https://api.panoramax.xyz/api/) (CC BY-SA, no key); Mapillary (needs a token) | Rome coverage unknown |
| Antenna positions (partial) | OSM: **191** mobile-mast nodes in Roma Capitale (C=80) ([tag wiki](https://wiki.openstreetmap.org/wiki/Tag:man_made%3Dmast)); [OpenCelliD](https://opencellid.org) (crowd-sourced) | Compare ~3,678 sites in Rome province ([ARPA Lazio](https://www.arpalazio.it/documents/20124/51651/IMPIANTI_RF_CEM_2024.pdf), C=70). OSM covers a small share (ratio C=30) |
| Context POIs | OSM (schools, kindergartens, hospitals, clinics, nursing homes, playgrounds) | Completeness unknown [inf] |
| Schools registry | [MIM anagrafe](https://dati.istruzione.it/opendata/opendata/catalogo/elements1/leaf?area=Scuole&datasetId=DS0400SCUANAGRAFESTAT) (IODL 2.0) | Coordinates present? C=40 |
| Natura 2000 | [EEA](https://www.eea.europa.eu/data-and-maps/data/natura-10) | Download as SHP/GPKG |

### Does not exist, is closed, or was not found

| Data | Status |
|---|---|
| Official open antenna registry for Rome/Lazio | Not found. Lazio has no regional EMF catasto law ([ARPA Lazio 2024](https://www.arpalazio.it/documents/20124/51651/IMPIANTI_RF_CEM_2024.pdf), C=75). The national CEN was open to SNPA staff only in 2019 ([Ecoscienza](https://arpae.it/it/ecoscienza/numeri-ecoscienza/anno-2019/numero-4-2019/campi-elettromagnetici/e-in-via-di-realizzazione-il-catasto-nazionale-cem); 2026 status unknown) |
| Cartoradio.it bulk data/API | None seen. The data is aggregated and anonymised (C=60 that no download exists) |
| ARPA Lazio EMF measurements as CSV/API | Not found. Only monthly PDFs, e.g. [Boncompagni](https://www.arpalazio.it/documents/20124/154891/Monitoraggio+CEM+Boncompagni+202111.pdf) (C=70). You would have to type in a handful of points by hand |
| ARPA Lazio hourly air quality API | Not found |
| PRG layers: Rete Ecologica, Carta per la Qualità | No WMS/WFS endpoint found ([geoportale](https://geoportale.comune.roma.it) is live) |
| Landscape constraints (SITAP / Vincoli in Rete / PTPR) | Web viewer only (C=45) or login-gated (C=50) |
| Rome digital twin / Atlante 3D | Announced ([Turismo Roma](https://turismoroma.it/en/news/new-atlas-rome-city%E2%80%99s-future-digital-twin), [Ingenio](https://www.ingenio-web.it/articoli/il-progetto-di-rigenerazione-urbana-di-roma-il-digital-twin-per-trasformare-la-capitale/)); not downloadable |
| Open LiDAR/DSM of Rome | Not found |
| Free VHR satellite imagery of Rome | Maxar Open Data has no Rome event and is CC BY-NC ([AWS](https://registry.opendata.aws/vantor-open-data/)) |
| Legal, storable webcam frames | None found. Windy API requires images to be used only via its own URLs ([terms](https://api.windy.com/webcams/terms)) |
| OpenAQ without a key | v1/v2 are retired; v3 needs a key ([OpenAQ](https://api.openaq.org/v3/locations)) |

**Practical rule [inf, C=70]:** if the organisers ship a Challenge 02 dataset, it beats everything above. Fill missing fields such as authorisation status and technical data with **clearly labelled synthetic values**. Fill missing PRG and landscape layers with "not available as open data" (that gap is itself a finding to report).

---

## 4. Recommended architecture and build plan

### Architecture [inf, C=75]

| Layer | Choice | Why |
|---|---|---|
| Data prep | Python + DuckDB (spatial + H3) + GeoParquet → static GeoJSON | No server needed. Shared-map friendly. Download once, so no live Overpass calls ([Overpass limits](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html)) |
| Belief grid | ~100 m grid; physics prior + GP on the log residual; mean, std and P(E>15 V/m) | Same pattern as Criado et al. and Kapteyn et al. |
| API | FastAPI exposing tools as endpoints | Agent, voice and UI all call the same tools |
| Agent | Tool-calling loop (SDK you already know); fewer than ~10 tools with strict JSON schemas | GeoBenchX failures: geometry done by the LLM, poor refusals |
| Front end | deck.gl + MapLibre with building extrusion; optional Lovable shell for the chat panel | Lowest integration risk ([deck.gl](https://deck.gl/docs/api-reference/geo-layers/tile-3d-layer)). Precedent: [Hobart twin](https://afterrealism.pages.dev/work/digital-twin-hobart) won with MapLibre + one PMTiles file |
| Voice | ElevenLabs agent: webhook tools → FastAPI; client tools → move the map | Supported tool types ([docs](https://elevenlabs.io/docs/eleven-agents/customization/tools)) |

### EMF model in plain words [inf unless linked]

1. **Prior:** for each antenna, compute free-space field E ≈ √(30·EIRP)/d. Combine all antennas as a root-sum-square on the grid (C=60 on the parameters). Real EIRP, tilt and azimuth are unknown, so use typical sector values flagged as assumptions (C=55). Cartoradio IT uses the same family of method ([SmartWorld](https://www.smartworld.it/news/cartoradio-mappa-campi-elettromagnetici-italia-gratis.html)).
2. **Update:** fit a GP on log(measured/prior) at the few ARPA points. Work in log space (C=80).
3. **Output:** mean map, std map, and P(E > 15 V/m). 15 V/m is the current attention value; the legal limit is 20 V/m; 6 V/m is obsolete ([MIMIT FAQ](https://www.mise.gov.it/images/stories/documenti/FAQ_2024_campi_elettromagnetici_CCE.pdf), C=85). The [30 July 2026 MIMIT decree](https://www.mimit.gov.it/it/normativa/decreti-interministeriali/decreto-interministeriale-30-luglio-2026-nuovi-limiti-di-esposizione-ai-campi-elettromagnetici) is about how the per-operator emission limit is calculated; from its summary it does not appear to change the 15 V/m value (C=70, full text not read). Expect wide uncertainty bands: free-space worst case can overestimate by 10–20 dB in shadowed spots (C=45).
4. **Honesty check:** leave-one-out z-scores show whether the predicted std is calibrated (C=80 that this is the cheapest credible "probabilistic" proof).

### Build plan: ordered steps with go/no-go gates (no time estimates)

1. **Gate 0, decide.** Answer the open questions in section 8. Lock: Challenge 02 + one main sponsor prize.
2. Make the public repo with an open licence and a README data table (source, licence, verified or not).
3. Pre-fetch and cache: Overture/OSM buildings for a central-Rome bbox, OSM context POIs, OSM + OpenCelliD antenna positions (or the challenge data), Natura 2000, an air-quality snapshot.
   - **Gate A:** every layer loads locally as GeoJSON. **No-go:** if antenna positions are missing, use challenge data or labelled synthetic data. Do not start scraping.
4. 3D map: extruded buildings + antenna points + context POIs.
   - **Gate B:** the map renders smoothly on the demo laptop. **No-go:** drop 3D and go 2D. Do not debug WebGL for long.
5. Tool `context_check(lat, lon, 300 m)`: counts and lists sensitive sites, Natura 2000 overlap, and "layer not available" for PRG and landscape constraints.
6. EMF belief grid (prior → GP → P(exceed)).
   - **Gate C:** the LOO check runs. **No-go:** ship the prior only, with a wide band labelled "uncalibrated".
7. Agent: geocode → context_check → emf_lookup → Exa regulation search → cited report. It also draws the 300 m circle on the map and shows the tool trace.
   - **Gate D:** end-to-end works for 3 scripted Rome addresses. **Go:** freeze scope, deploy, record the 3-minute video, publish layers as GeoJSON.
8. Stretches, in this order, only after Gate D:
   - (a) Air-quality belief grid: Open-Meteo prior + Sensor.Community points.
   - (b) ElevenLabs voice.
   - (c) Thesis demo (section 5).
   - (d) Sentinel-2 layer.
   - (e) Google 3D Tiles backdrop.
9. Rehearse with an offline fallback (cached GeoJSON, recorded backup). Plan for venue Wi-Fi, cold-started free hosts and noisy-room voice failures (C=70).

---

## 5. Placing your multi-view fusion thesis honestly

**The fact that decides this:** every strong multi-view detection method (MVDet → SCFusion) needs **overlapping, calibrated cameras**. They are benchmarked almost only on WildTrack (7 cameras) and MultiviewX (synthetic) ([arXiv](https://arxiv.org/pdf/2509.08421)). Public Rome webcams almost never overlap or come with calibration [inf, C=75]. One static webcam gives you a depth map, not multi-view 3D (C=85).

**Honest framing [inf, C=80]:** your thesis is the **fusion engine** of the twin. Each sensor (antenna model, ARPA point, low-cost PM sensor, and optionally a camera) is an observation with its own error model, fused into one shared ground-plane grid. That is the same maths as camera occupancy fusion (sum log-odds or Gaussian beliefs per cell). The FAA webcam-to-Bayesian-analysis pipeline is the closest real-world precedent ([Carley et al.](https://www.cambridge.org/core/product/3303F8BEC7EB9BDCF7D412FF11F238D9/core-reader)).

**Two optional showcases, after Gate D:**

| Option | What | Honest label |
|---|---|---|
| A. WildTrack replay | Run a pre-trained MVDet/EarlyBird/TrackTacular model ([MVDet](https://arxiv.org/abs/2007.07247), [bg] C=85) | "Thesis-class method on the standard benchmark" (C=70 that it runs) |
| B. 2 webcams, one piazza | Hand-click 6–12 points against the AGEA orthophoto, RANSAC homography, YOLO foot-points onto the grid, uncertainty growing with distance ([TrafficLab-3D](https://yuk068.github.io//2026/02/20/traffilclab-3d-overview)) | "Multi-sensor fusion on a common ground plane", **not** "multi-view detection" (C=85) |

For option B, keep counts only, hold frames in memory only, and show no frames (see risks). Register to the orthophoto or OSM, never to Google tiles (C=75).

**Antenna link (optional, C=50):** use SAM 3 or Grounding DINO on street photos to propose "candidate antennas" with a detection probability. Feed them into the prior as uncertain sources. Rooftop panels at 20–50 cm orthophoto resolution are borderline (C=60).

---

## 6. Agents, Exa and ElevenLabs used meaningfully

**Agent design rule:** the LLM orchestrates and explains. Tools compute the 300 m buffers, counts and fields. GeoBenchX found models fail on geometric relations and rarely refuse tasks they cannot solve ([GeoBenchX](https://arxiv.org/html/2503.18129v2)). So build an explicit "insufficient data" answer and show the tool trace in the UI (C=70).

| Agent / sponsor | Meaningful role [inf] | C |
|---|---|---|
| Permit-context agent | Address → context_check → EMF belief → Exa regulation search → report with citations and uncertainty | 70 |
| Data-scout agent | Exa finds new open datasets; a tool checks the licence and format, then ingests to DuckDB | 60 |
| **Exa** | Citations inside the core report (L. 214/2023, the 30 Jul 2026 decree, Rome rules). The keyless MCP is at `mcp.exa.ai/mcp`, with free rate limits ([Exa docs](https://exa.ai/docs/get-started/exa-mcp.md)). Pricing comes from a competitor page (C=60) | 70 |
| **ElevenLabs** | Voice Q&A for non-technical citizens: "Can an antenna go at Via X?" Webhook tools call your API; client tools fly the map ([webhook docs](https://elevenlabs.io/docs/eleven-agents/customization/tools/server-tools)). The API must be public. Free-tier limits and Italian voice quality were not verified | 60 |
| Lovable | Shell UI and chat panel only. Keep the map hand-written. No evidence was found on how well Lovable handles deck.gl/Cesium | 50 |
| Avalanche | No meaningful fit found [inf] | 70 |

Judges' sponsor criteria are unknown. "Core flow, not gimmick" is the safe reading (C=55). Pick **Exa** as the main sponsor target, because it is already part of the core flow [inf, C=65].

---

## 7. Main risks

| Risk | What to do | C |
|---|---|---|
| **Google 3D Tiles terms** | No analysis, no extracting geodata, no 3D models derived from them, no caching. Show attribution. Billing must be enabled ([policies](https://developers.google.com/maps/documentation/tile/policies), [billing](https://developers.google.com/maps/documentation/tile/usage-and-billing?authuser=6)). Promo videos are allowed only if ≤30 s, so a 3-minute video showing them may conflict [inf]. Never put the key or cached tiles in the public repo | 80 (terms), 50 (video point) |
| **Webcam GDPR / ToS** | The Garante treats video as personal data ([docweb 10014032](https://www.garanteprivacy.it/home/docweb/-/docweb-display/docweb/10014032)). The old 2001 beach-cam decision allowed only cams that cannot identify people ([doc 41782](https://garanteprivacy.it/garante/doc.jsp?ID=41782), applicability C=40). Use counts only, no stored frames, or skip webcams. Not legal advice | 60 |
| **No official open antenna data** | OSM covers a small share. OpenCelliD is crowd-sourced (licence not verified). Label positions "indicative, not official" and use synthetic data for authorisation fields | 70 |
| **Cartoradio.it as benchmark** | Launched 10 Sep 2026 by MIMIT/FUB: estimated E on 100 m cells, quarterly operator data, aggregated and anonymised, modelled not measured ([Punto Informatico](https://www.punto-informatico.it/campi-elettromagnetici-cartoradio-cerca-indirizzo/)). Compare visually only; do not scrape. Your edge is uncertainty, the context check, open code and agents | 85 |
| **300 m used as a ban** | Rulings limit municipalities to siting criteria, not general bans. Present distance as context only | 70 |
| **EMF numbers misread as official** | Disclaimer: "model estimate, ARPA certifies." Use two tiers: a citizen view on a 100 m grid and an office view with exact data | 70 |
| **Live demo failure** | Pre-cache everything, use scripted addresses, record a backup ([judge notes](https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l), C=60) | 70 |
| **Licence mixing** | ODbL (OSM/Overture) means share-alike on derived databases [bg, C=75]. CC BY-NC (Maxar) and Esri imagery break the open rule | 75 |

---

## 8. Open questions for you

1. **Team size?** Alone, stop at Gate D plus one stretch. With 3 people, split roles: data/model, agent/API, front end/video [inf].
2. **GPU access?** None is needed for the core. A GPU is only needed for thesis option A/B with heavier models, or for VGGT/splat experiments.
3. **What does your thesis method need exactly?** Overlapping views? Known intrinsics and extrinsics? A ground-plane assumption? Synchronised frames? If it needs overlap plus calibration, only WildTrack (option A) is honest.
4. **Challenge 02 strictly, or your own project?** Challenge 02 gives a clear user and impact story. Your own twin has a weaker "useful to Rome" case [inf, C=65].
5. **Which sponsor prize?** Recommended: Exa first, ElevenLabs second.
6. **Did the organisers release a Challenge 02 dataset?** Check its schema and licence first. It changes Gate A.
7. **Can the organisers confirm** that webcam-derived counts are allowed under "no personal data"?
8. **Google 3D Tiles:** do you have a billing-enabled key, and do you accept the attribution and video limits? If not, skip them.

---

## Sources

- Google Map Tiles: [policies](https://developers.google.com/maps/documentation/tile/policies) · [usage & billing](https://developers.google.com/maps/documentation/tile/usage-and-billing?authuser=6) · [pricing](https://developers.google.com/maps/billing-and-pricing/pricing?authuser=1)
- deck.gl [Tile3DLayer](https://deck.gl/docs/api-reference/geo-layers/tile-3d-layer) · Cesium splats [RadianceFields](https://radiancefields.com/cesium-adds-hierarchical-lod-for-gaussian-splats-to-3d-tiles-cesiumjs-and-cesium-for-unreal) · [Hobart twin](https://afterrealism.pages.dev/work/digital-twin-hobart)
- [Overpass usage](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html) · [Overture buildings](https://docs.overturemaps.org/guides/buildings) · [GlobalBuildingAtlas](https://un-spider.org/news-and-events/news/globalbuildingatlas-open-global-3d-buildings-data-digital-twins-and-disaster)
- 3D research: [EOGS++](https://arxiv.org/html/2511.16542v1) · [Skyfall-GS](https://arxiv.org/html/2510.15869v2) · [CityGaussianV2](https://arxiv.org/html/2411.00771v2) · [VGGT-Ω](https://arxiv.org/abs/2605.15195) · [MapAnything](https://arxiv.org/pdf/2509.13414v3) · [WildGaussians](https://arxiv.org/html/2407.08447v2)
- Multi-view & cross-view: [SCFusion](https://arxiv.org/pdf/2509.08421) · [MVDet](https://arxiv.org/abs/2007.07247) · [VIRD](https://arxiv.org/html/2603.12918) · [TrafficLab-3D](https://yuk068.github.io//2026/02/20/traffilclab-3d-overview) · [NVIDIA VSS calibration](https://docs.nvidia.com/vss/3.0.0/smartcity-docs/3.0.0/Calibration.html)
- Probabilistic: [Kapteyn et al. 2021](https://www.nature.com/articles/s43588-021-00069-0) · [Criado et al. 2023](https://gmd.copernicus.org/articles/16/2193/2023/) · [Carley et al.](https://www.cambridge.org/core/product/3303F8BEC7EB9BDCF7D412FF11F238D9/core-reader)
- EMF: [MIMIT FAQ 2024](https://www.mise.gov.it/images/stories/documenti/FAQ_2024_campi_elettromagnetici_CCE.pdf) · [MIMIT decree 30 Jul 2026](https://www.mimit.gov.it/it/normativa/decreti-interministeriali/decreto-interministeriale-30-luglio-2026-nuovi-limiti-di-esposizione-ai-campi-elettromagnetici) · [ARPAE/AIRP](https://aggiornati.arpae.it/it/notizie/notari-convegno-airp-contributo.pdf) · [cartoradio.it](https://www.cartoradio.it/) · [SmartWorld](https://www.smartworld.it/news/cartoradio-mappa-campi-elettromagnetici-italia-gratis.html) · [Punto Informatico](https://www.punto-informatico.it/campi-elettromagnetici-cartoradio-cerca-indirizzo/) · [ARPA Lazio 2024](https://www.arpalazio.it/documents/20124/51651/IMPIANTI_RF_CEM_2024.pdf) · [Ecoscienza 2019](https://arpae.it/it/ecoscienza/numeri-ecoscienza/anno-2019/numero-4-2019/campi-elettromagnetici/e-in-via-di-realizzazione-il-catasto-nazionale-cem) · [Il Post 2025](https://www.ilpost.it/2025/06/23/piano-comune-roma-antenne-tetti/) · [ExposNet](https://arxiv.org/pdf/2503.02966) · [Electronics 2025](https://mdpi-res.com/d_attachment/electronics/electronics-14-04766/article_deploy/electronics-14-04766.pdf) · [Sensors 2024](https://mdpi.com/1424-8220/24/23/7849) · [Sionna RT](https://nvlabs.github.io/sionna/examples/Sionna_Ray_Tracing_Coverage_Map.html) · [Geo2SigMap](https://github.com/functions-lab/geo2sigmap) · [ANFR open data](https://data-backoffice.anfr.fr/fr/dataset/observatoire_des_reseaux_mobiles/resource/96d6de02-a531-4cff-82c1-64e0f9976206) · [OSM mast tag](https://wiki.openstreetmap.org/wiki/Tag:man_made%3Dmast)
- Data: [CDSE STAC](https://stac.dataspace.copernicus.eu/v1/) · [CDSE quotas](https://documentation.dataspace.copernicus.eu/Quotas.html) · [IRIDE/ESA](https://www.esa.int/Applications/Observing_the_Earth/IRIDE/Italy_s_Earth_monitoring_programme_reaches_new_milestone) · [IRIDE/Startmag](https://en.startmag.it/spazio-e-difesa-2/iride-becomes-operational-satellite-data-and-geospatial-services-from-asi-launched/) · [Maxar Open Data](https://registry.opendata.aws/vantor-open-data/) · [Lazio WMS](https://geoportale.regione.lazio.it/geoserver/ows?service=WMS&request=GetCapabilities) · [TINITALY](https://tinitaly.pi.ingv.it/) · [Open-Meteo AQ](https://air-quality-api.open-meteo.com/v1/air-quality?latitude=41.9&longitude=12.5&current=pm10,pm2_5,european_aqi) · [Sensor.Community](https://data.sensor.community/airrohr/v1/filter/box=41.99,12.35,41.78,12.62) · [dati.lazio.it](https://dati.lazio.it/api/3/action/package_search?q=aria) · [Roma Mobilità](https://romamobilita.it/it/tecnologie/open-data) · [Panoramax](https://api.panoramax.xyz/api/) · [Windy terms](https://api.windy.com/webcams/terms) · [MIM schools](https://dati.istruzione.it/opendata/opendata/catalogo/elements1/leaf?area=Scuole&datasetId=DS0400SCUANAGRAFESTAT) · [EEA Natura 2000](https://www.eea.europa.eu/data-and-maps/data/natura-10) · [Atlante di Roma](https://turismoroma.it/en/news/new-atlas-rome-city%E2%80%99s-future-digital-twin)
- Agents & sponsors: [GeoBenchX](https://arxiv.org/html/2503.18129v2) · [CityLLM](https://www.alphaxiv.org/abs/2607.14542.md) · [Exa MCP](https://exa.ai/docs/get-started/exa-mcp.md) · [Exa pricing (competitor)](https://parallel.ai/articles/exa-alternatives) · [ElevenLabs tools](https://elevenlabs.io/docs/eleven-agents/customization/tools) · [ElevenLabs webhooks](https://elevenlabs.io/docs/eleven-agents/customization/tools/server-tools)
- Vision: [SAM 3](https://www.emergentmind.com/papers/2511.16719) · [Cell-tower detection](https://arxiv.org/abs/2311.07840)
- Privacy & judging: [Garante 41782](https://garanteprivacy.it/garante/doc.jsp?ID=41782) · [Garante 10014032](https://www.garanteprivacy.it/home/docweb/-/docweb-display/docweb/10014032) · [Judging notes](https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l)
