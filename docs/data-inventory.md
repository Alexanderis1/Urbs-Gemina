# Build Rome's twin from verified open feeds

**How to read this.** **C=NN** is a confidence score from 1 to 100. **[bg]** is background knowledge, not re-checked. **[inf]** is an inference or judgement. "VERIFIED" means a researcher got real data from the endpoint on 13 Nov 2026. Prices are in USD unless marked EUR. No time or effort estimates appear anywhere: plans are ordered steps with go/no-go gates.

---

## 1. Bottom line

**You can build a real, technically valid, open digital twin of Rome with zero spend.** A paid stereo purchase is what moves it from "good" to "true 3D". Recommended build [inf, C=75]:

- **Geometry:** an open LoD1 model of all of Rome (Overture/OSM footprints + GlobalBuildingAtlas heights, checked against Urban Atlas). Add **georeferenced Gaussian splats of 3–5 landmarks** from MegaScenes' ready-made COLMAP models. Optional: a **purchased Pléiades Neo tri-stereo archive set (≈$1,375 for 25 km²)** gives a true DSM and LoD2 roofs for the historic centre.
- **Live layer:** a probabilistic "belief" store. Each layer (transit delay, road speed, air quality, rain, EMF, activity) keeps a mean and an uncertainty, updated from feeds that work today: GTFS-RT, EEA hourly air quality, DPC radar, Open-Meteo/CAMS, Bird GBFS, Sentinel-2 and others.
- **Scenarios:** SUMO traffic through an existing SUMO MCP server; EMF from a free-space prior plus Sionna RT, returned as ranges; accessibility, noise, shadow and viewshed as extras.
- **Antenna challenge:** the full 300 m context check runs on **official open layers that DO exist**: the Roma Capitale and Regione Lazio GeoServers plus MiC SITAP. Antenna positions remain crowd-sourced estimates. Authorisation status stays synthetic, with a FOIA route.
- **Interface:** Lovable front end → Supabase edge functions → Python tool API on Modal. Exa supplies citations and a news "text sensor". An ElevenLabs voice agent shares the same tools and guardrails. Avalanche Fuji hash-anchors data snapshots, runs and reports.

Spend tiers: **$0** (everything above except the stereo DSM), **≈$230** (GPU budget + Lovable Pro + ElevenLabs Creator + BestTime), **≈$1.6k recommended** (adds the tri-stereo DSM). Details are in section 4.

---

## 2. What changed since the first report

The first report recommended a **narrow antenna-only twin** and cut 3D reconstruction. The new findings overturn several of its "not available" verdicts. This report replaces its scope advice.

| First report said | Now (verified 13 Nov 2026) |
|---|---|
| PRG, Rete Ecologica, Carta per la Qualità: no endpoint | **Roma Capitale GeoServer** ([WFS caps](https://geoportale.comune.roma.it/geoserver/ows?service=WFS&version=1.0.0&request=GetCapabilities)) serves them, plus UNESCO, schools, nidi, hospitals and municipi. No authentication needed |
| SITAP / PTPR: viewer only or login-gated | **Lazio GeoServer** serves PTPR Tavola A/B and Natura 2000 by WFS. **SITAP WFS works** |
| No ARPA hourly air-quality API | **EEA Download Service** returns hourly Parquet for **13 Rome NO2 sampling points**, with rows up to 03:00 today. ARPA has yearly hourly TXT files for 1999–2025 |
| School coordinates: C=40 | Roma layer has **916 state schools** with MIM code, plus 390 nidi and 333 infanzia, all with point geometry |
| Roma Mobilità licence unchecked | GTFS-RT **decodes** (1,258 vehicles). Licence is **CC BY-SA** |
| Cut 3D reconstruction and splats | **MegaScenes has ~896 Rome scenes with solved camera poses.** Landmark splats are now realistic on your compute. Whole-city splats are still not |
| Free VHR / DSM: not available | Still no free VHR. **Paid tri-stereo is affordable** (≈$1,375 for 25 km²) |
| Cartoradio: no bulk data | The data is one public GeoTIFF, but its **legal notes forbid reuse**. Still do not use it |
| Avalanche: no meaningful fit | **Hash-anchoring** snapshots, runs and reports is a real provenance use |
| Lovable: chat shell only | **Full front end** with Supabase edge functions. Git sync works on the Free plan |
| Exa price from a competitor page | Official prices now confirmed (section 4) |
| OpenCelliD licence unverified | **CC BY-SA 4.0**, token-gated, with a tokenless PMTiles mirror |
| Thesis demos as stretch goals | Dropped. Multi-view work appears naturally in landmark reconstruction (section 5) |

**EMF threshold conflict, resolved.** One note quotes the text of DPCM 8 July 2003: a 6 V/m attention value and quality goal, with 6-minute averaging ([DPCM text, ARPA Campania copy](https://www.arpacampania.it/documents/20182/261099/06.+DPCM+8+luglio+2003+protezione+pubblico+campi+a+radiofrequenza.pdf/e8b8c373-6354-4234-80da-3c624f422bd8)). That figure is **outdated**. **L. 214/2023 art. 10** (in force since 2024) raised it to **15 V/m, averaged over 24 hours**, in buildings with prolonged stay and their outdoor pertinences. The exposure limit stays **20 V/m** ([MIMIT FAQ 2024](https://www.mise.gov.it/images/stories/documenti/FAQ_2024_campi_elettromagnetici_CCE.pdf); [ARPAE/AIRP](https://aggiornati.arpae.it/it/notizie/notari-convegno-airp-contributo.pdf); [L. 214/2023](https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2023-12-30;214)). **Use 15 V/m as current (C=85).** The MIMIT decree of 30 July 2026 has not been read ([MIMIT page](https://www.mimit.gov.it/it/normativa/decreti-interministeriali/decreto-interministeriale-30-luglio-2026-nuovi-limiti-di-esposizione-ai-campi-elettromagnetici)). So store every threshold in a **config file with a citation and an "as of" date**, never in code or prompts.

---

## 3. Data inventory (the core)

Status key: **VERIFIED** = live data on 13 Nov 2026. **Key** = needs a free or paid key. **Untested** = documented but not called. **Closed** = not public, or the terms forbid the use.

### 3a. 3D, base geometry and imagery

| Source | What you get | Access & licence | Status |
|---|---|---|---|
| [Overture buildings](https://docs.overturemaps.org/guides/buildings) ([STAC](https://stac.overturemaps.org/catalog.json)) | Footprints, some heights, release 2026-10-21 | Download; ODbL | VERIFIED catalogue. Rome height completeness unknown (C=40) |
| [OpenStreetMap](https://www.openstreetmap.org/api/capabilities) | Buildings, roads, POIs | ODbL | VERIFIED API. Overpass unreachable from the sandbox; retry from the venue |
| [GlobalBuildingAtlas](https://github.com/zhu-xlab/GlobalBuildingAtlas) | LoD1 heights for every building, 3 m raster, ~2019 imagery, RMSE 1.5–8.9 m ([UN-SPIDER](https://un-spider.org/news-and-events/news/globalbuildingatlas-open-global-3d-buildings-data-digital-twins-and-disaster)) | Download; open (C=70) | Untested this round |
| [Urban Atlas Building Height 2012](https://copernicus.discomap.eea.europa.eu/ArcGIS/rest/services/UrbanAtlas/UA_BuildingHeights_2012_10m/ImageServer?f=pjson) | 10 m height raster from IRS-P5 stereo, core Rome | ImageServer; Copernicus open (C=80) | VERIFIED (3 m returned at 12.52E, 41.88N) |
| Copernicus DEM GLO-30 / [TINITALY 10 m](https://tinitaly.pi.ingv.it/) | Terrain | Free; CC BY (C=75) | TINITALY site VERIFIED earlier |
| [Lazio AGEA orthophoto WMS](https://geoportale.regione.lazio.it/geoserver/ows?service=WMS&version=1.3.0&request=GetMap&layers=geonode:2023_AGEA_25833_COG&styles=&crs=EPSG:4326&bbox=41.88,12.47,41.91,12.51&width=512&height=512&format=image/jpeg) | ~20 cm orthophoto, 2008–2023; texture and control points. No 3D (it is orthorectified) | WMS; licence C=60 open with attribution | VERIFIED (GetMap) |
| [Agenzia Entrate cadastral WMS](https://wms.cartografia.agenziaentrate.gov.it/inspire/wms/ows01.php?service=WMS&request=GetCapabilities) | Cadastral parcels and buildings | WMS; CC BY 4.0 (C=70) | VERIFIED caps |
| [Sentinel-2 via CDSE STAC](https://catalogue.dataspace.copernicus.eu/stac/collections/sentinel-2-l2a/items?bbox=12.3,41.8,12.6,42.0&limit=1&sortby=-datetime) | 10 m optical; a same-day scene (13 Nov, 10:12Z) | Free account to download | VERIFIED |
| [ESA WorldCover 2021 tile](https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_N39E012_Map.tif) | 10 m land cover | CC BY 4.0 (C=85) | VERIFIED |
| [MegaScenes](https://registry.opendata.aws/megascenes/) (`s3://megascenes`, [categories.json](https://megascenes.s3.amazonaws.com/metadata/categories.json)) | ~896 Rome scenes with COLMAP models: Pantheon (28027), Forum Romanum (216043), Trajan's Column, Piazza Navona, Spagna, Vittoriano, St Peter's, Castel Sant'Angelo, Arch of Constantine | No-sign S3; CC BY 4.0, plus each photo's own Wikimedia licence | VERIFIED bucket reads. Colosseum and Trevi not found under obvious names (C=50) |
| [Mapillary](https://help.mapillary.com/hc/en-us/articles/115001770409-Licenses) | Street images with computed poses; faces and plates blurred [bg C=85] | API token; CC BY-SA | Key. Rome density not measured |
| Wikimedia Commons geosearch | Extra landmark photos with per-file licence [bg C=85] | Free API | Untested |
| Phototourism / IMC, 1DSfM | Trevi, Colosseum, St Peter's Sq., Pantheon, Forum, Popolo [bg C=75] | Research licences, unclear (C=50) | Use for validation only |
| [ISTAT 2021 census sections](https://www.istat.it/storage/cartografia/basi_territoriali/2021/R12_21.zip) | Lazio sections (also 13,656 in the Roma layer) | CC BY 4.0 (C=80) | VERIFIED |
| [Satellogic EarthView](https://arxiv.org/html/2501.08111v1) | 1 m, 2022 | CC BY 4.0 | Italy coverage unconfirmed |
| [Umbra open SAR](https://registry.opendata.aws/umbra-open-data/) | SAR | CC BY | No Rome task found (C=80) |
| MASE PST LiDAR ([spec](https://mase.gov.it/sites/default/files/archivio/bandi/pst_2013_disciplinare_tecnico.pdf)) | 1 m DTM along rivers | WMS returned 403/500 | Closed or unreachable. Request formally |

**Gap:** no open LiDAR or DSM of Rome, and no free multi-view VHR. Real roof geometry must be bought (section 4) or requested from Regione Lazio / Roma Capitale (C=50 that they hold it).

### 3b. Antenna and EMF

| Source | What you get | Access & licence | Status |
|---|---|---|---|
| [OpenCelliD downloads](https://opencellid.org/downloads.php) ([format](https://wiki.opencellid.org/wiki/Database_format)) | **Estimated cell centroids**: radio, MCC/MNC, LAC/TAC, cell ID, lat/lon, range, samples. Last 18 months only | Free token; **CC BY-SA 4.0**; visible credit required | Download page VERIFIED. Rome count not obtained |
| [OpenCelliD PMTiles mirror](https://data.source.coop/smartmaps/opencellid/cellid.pmtiles) ([Source Cooperative](https://source.coop/smartmaps/opencellid)) | Same data, no token, 534 MB, updated 21 Aug 2025 | CC BY-SA 4.0 | VERIFIED (HTTP 200) |
| [beaconDB](https://beacondb.net/) | 6.8M towers worldwide | Public domain (per the site) | Site VERIFIED. Export path untested |
| OSM `man_made=mast` / `tower:type=communication` | ~191 mobile masts in Roma Capitale (C=80) | ODbL | Counted earlier. Overpass untested today |
| [LTE Italy](https://lteitaly.it/), [CellMapper](https://www.cellmapper.net/) | Per-operator site maps | Private; no export | Closed for reuse |
| [cartoradio.it](https://www.cartoradio.it/map) (MIMIT/FUB) | National 100 m E-field estimate grid as one COG GeoTIFF (176 MB, modified 8 Sep 2026) | **[Legal notes](https://www.cartoradio.it/note-legali) forbid reproducing or reusing maps and data for other purposes** | VERIFIED (HEAD only). **Link out only** |
| [ARPA Lazio EMF monitoring PDFs](https://www.arpalazio.it/documents/20124/154891/Monitoraggio+CEM+Boncompagni+202110.pdf) | Fixed station on the Via Boncompagni roof; graphs only | PDF | VERIFIED. No tabular V/m values |
| [ARPA Lazio site counts](https://www.arpalazio.it/documents/20124/51651/Impianti_RF_CEM_2018.pdf) | 4,137 SRB sites in Lazio (2018). Earlier round: ~3,678 in Rome province, 2024 (C=70) | PDF | VERIFIED |
| Infratel 4G/5G coverage map ([news](https://www.tuttoandroid.net/news/2026/01/20/infratel-mappa-interattiva-copertura-reti-mobili-4g-5g-1136189/)), [AGCOM maps](https://maps.agcom.it/) | Coverage, not sites | Unknown | Untested |
| Official SRB registry (Roma, Lazio, ISPRA CEN) | Positions, authorisation status | dati.comune.roma.it returns **0 results** | **Closed. FOIA only** |

**Gap:** no official antenna positions, EIRP, tilt, azimuth or authorisation status. OpenCelliD centroids are often 100 m–1 km from the real mast (C=70 [inf]).

### 3c. Regulatory and context layers for the 300 m check

Roma Capitale GeoServer: [`https://geoportale.comune.roma.it/geoserver/ows`](https://geoportale.comune.roma.it/servizi/). Use WFS 1.0.0 (lon,lat order). Layers are often stored in EPSG:3004, so request `srsName=EPSG:4326`.

| Layer (typeName) | What you get | Count | Status |
|---|---|---|---|
| `DIPAU:PrgSistemiRegole10000` (WMS GetFeatureInfo) | PRG component plus a link to the NTA article | WMS only | VERIFIED (Piazza Venezia → NTA Art. 42) |
| `DIPAU:CartaPerLaQualita_*` | Morphologies 155, pre-existing features 4,629, open spaces 1,414, archaeology, special buildings | see left | VERIFIED |
| `DIPAU:ReteEcologicaPoligono` / `...Linea` | Rete Ecologica components | 1,209 / 140 | VERIFIED |
| `SOVR:SitoUnescoPoly`, `SOVR:buffer_zone` | UNESCO historic centre and buffer zone | 16 / 4 | VERIFIED |
| `DIPSCU:mv_portale_rete_statale` | State schools with MIM code | 916 | VERIFIED |
| `DIPSCU:mv_portale_nidi_capitolini`, `...infanzia_capitolina` | Nidi, scuole dell'infanzia | 390 / 333 | VERIFIED |
| `DIPAMB:Ospedali` | Hospitals with bed counts | 38 (looks incomplete, C=60) | VERIFIED |
| `DIPPC:241_ServiziSanitarieAssistenziali` | Health and care facilities. **Has personal contact fields: drop them** | 21 | VERIFIED |
| `DIPPC:235_AreeProtette` | Protected areas | 21 | VERIFIED |
| `DIPPC:210_RomaCapitale_Municipi`, `DIPDIT:ZoneUrbanistiche` | Municipi, urban zones | 15 / 155 | VERIFIED |
| `REGLAZ:tavola_a_paesaggi` | PTPR Tavola A (cascaded from Lazio) | 15,253 | VERIFIED |
| `DIPAMB:ZonizzazioneAcustica` | Acoustic zoning (2002) | — | Listed, not hit-tested |

Other servers:

| Source | What you get | Access & licence | Status |
|---|---|---|---|
| [Lazio GeoServer WFS](https://geoportale.regione.lazio.it/geoserver/ows?service=WFS&version=1.0.0&request=GetCapabilities) | PTPR Tavola A/B: woods (16,927), DM protection areas, centri storici, archaeology, public waters, usi civici; `geonode:rete_natura200000` (202 in Lazio; IT6030052 Villa Borghese e Villa Pamphili sits in the central box) | Free; licence not read | VERIFIED |
| [MiC SITAP](https://sitap.cultura.gov.it/geoserver/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=sitap_ws_clone:LAZIO_art_136_c_d&maxFeatures=5&outputFormat=application/json) | Art. 136/142 D.Lgs. 42/2004 constraints (Lazio art. 136: 315) | Free | VERIFIED |
| [Vincoli in Rete](http://vincoliinrete.beniculturali.it/geoserver/ows) | Archaeological and monumental constraints | WMS only; WFS returns 401 | VERIFIED (WMS) |
| [EEA Natura 2000 REST](https://bio.discomap.eea.europa.eu/arcgis/rest/services/ProtectedSites/Natura2000Sites/MapServer?f=json) | Natura 2000 fallback | Open (C=70) | VERIFIED |
| OSM `amenity=nursing_home`, `leisure=playground` | **RSA and playgrounds**: no official layer exists | ODbL | Query untested (Overpass blocked) |
| [dati.comune.roma.it nidi CSV](https://dati.comune.roma.it/catalog/dataset/b5ec3077-f30a-4c98-9330-68c92595fd03/resource/844f44e3-9e13-453a-b6c6-e7799363de47/download/opendata_2022_23_nido.csv) | Nidi 2022–23, addresses only | CC BY | VERIFIED |

Example tested call (state schools in the 300 m box around Piazza Venezia):
`https://geoportale.comune.roma.it/geoserver/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=DIPSCU:mv_portale_rete_statale&bbox=12.4787,41.8933,12.4859,41.8987,EPSG:4326&outputFormat=application/json`. Query by bbox, then compute exact distances client-side (the DWITHIN test returned 0).

**Gaps:** no licence statement in the GeoServer capabilities (C=60 that CC BY applies, as on the CKAN portal); PRG Sistemi e Regole is WMS-only; there is no official RSA or playground layer.

### 3d. Environment: air, weather, hazards, Earth observation

| Source | What you get | Access & licence | Status |
|---|---|---|---|
| [EEA AQ Download API](https://eeadmz1-downloads-api-appservice.azurewebsites.net/swagger/index.html) (`POST /ParquetFile/urls`, `{"countries":["IT"],"cities":["Roma"],"pollutants":["NO2"],"dataset":1,...}`) | Hourly station data for 13 Rome NO2 points; unverified "E2a" rows up to today 03:00 | No key; EEA open (C=80) | VERIFIED |
| [ARPA Lazio hourly TXT](https://www.arpalazio.net/main/aria/sci/basedati/chimici/BDchimici/RM/DatiOrari/RM_NO2_2025.txt) | Hourly values by station, 1999–2025, 9 pollutants | No key; licence not stated | VERIFIED. **2026 file not found** |
| [ARPA daily report PDF](https://www.arpalazio.net/main/aria/sci/annoincorso/rpgg/RMC/2026/20261112RMC.pdf) | Daily values for Rome stations, up to 12 Nov | PDF | VERIFIED (needs parsing) |
| [Open-Meteo air quality](https://air-quality-api.open-meteo.com/v1/air-quality?latitude=41.9&longitude=12.5&hourly=pm10,pm2_5,nitrogen_dioxide) | CAMS Europe ~10 km hourly forecast: PM, NO2, O3, AQI, UV, pollen, dust | No key; CC BY 4.0; 10k calls/day free, non-commercial | VERIFIED (use `nitrogen_dioxide`, not `no2`) |
| [CAMS Europe (ADS)](https://ads.atmosphere.copernicus.eu/api/catalogue/v1/collections/cams-europe-air-quality-forecasts) | 0.1° analysis plus 4-day forecast; reanalyses | Free key; CC BY 4.0 | Catalogue VERIFIED |
| [Sensor.Community](https://data.sensor.community/airrohr/v1/filter/area=41.9,12.5,15) | ~10 low-cost PM/T/RH sensors | Free; ODbL (C=80) | VERIFIED |
| OpenAQ v3, WAQI, Airly, PurpleAir, IQAir | Aggregated / low-cost AQ | Key | Untested for Rome |
| [DPC radar API](https://radar-api.protezionecivile.it/findLastProductByType?type=VMI) | Rain rate and reflectivity GeoTIFF, 5 min, ~10 min latency | No key; CC BY (C=75) | VERIFIED |
| [DPC alert bulletins](https://raw.githubusercontent.com/pcm-dpc/DPC-Bollettini-Criticita-Idrogeologica-Idraulica/master/README.md) | Daily hydro-geological alerts | CC BY 4.0 | README VERIFIED; file paths untested |
| [Open-Meteo forecast](https://api.open-meteo.com/v1/forecast?latitude=41.9&longitude=12.5&current=temperature_2m) / [archive](https://archive-api.open-meteo.com/v1/archive?latitude=41.9&longitude=12.5&start_date=2020-01-01&end_date=2020-01-02&hourly=temperature_2m) / [flood](https://flood-api.open-meteo.com/v1/flood?latitude=41.9&longitude=12.5&daily=river_discharge) | Weather; GloFAS discharge | No key; CC BY 4.0 | VERIFIED (then 429 from the shared IP) |
| [ECMWF open data](https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com/?list-type=2&prefix=20261113/&delimiter=/&max-keys=5) | 0.25° forecast fields, 4 runs per day | CC BY 4.0 (C=85) | VERIFIED |
| [Lazio CFR network](https://regione.lazio.it/protezione-civile/centro-funzionale-regionale/rete-idrometeorologica) | 207 rain gauges, 82 hydrometers (Tiber at Ripetta), 15 min | Viewer only, no API | Closed for machines |
| [Landsat 8/9 surface temperature (Planetary Computer)](https://planetarycomputer.microsoft.com/api/stac/v1/search?collections=landsat-c2-l2&bbox=12.3,41.8,12.6,42.0&limit=1&sortby=-datetime) | Land surface temperature, latest 5 Nov | Free token | VERIFIED search |
| [ECOSTRESS](https://cmr.earthdata.nasa.gov/search/granules.json?short_name=ECO_L2T_LSTE&bounding_box=12.3,41.8,12.6,42.0&sort_key=-start_date&page_size=1) / [Black Marble](https://cmr.earthdata.nasa.gov/search/granules.json?short_name=VNP46A2&bounding_box=12.3,41.8,12.6,42.0&sort_key=-start_date&page_size=1) | ~70 m LST; night lights | Earthdata login | VERIFIED search |
| [ISPRA IdroGEO](https://idrogeo.isprambiente.it/api/pir/comuni/058091) | Rome flood/landslide exposure statistics (e.g. 389,737 residents in low-probability flood areas, C=65 on field meaning) | No key | VERIFIED |
| [INGV FDSN](https://webservices.ingv.it/fdsnws/event/1/query?format=text&limit=2&minlat=41.5&maxlat=42.3&minlon=12&maxlon=13&orderby=time) | Earthquakes | CC BY (C=75) | VERIFIED |
| [EGMS](https://egms.land.copernicus.eu/) | InSAR ground motion, 2020–2025 | EU Login | Site VERIFIED |
| [EFFIS WFS](https://maps.effis.emergency.copernicus.eu/effis?service=WFS&request=GetCapabilities) | Burnt areas, fire danger | Open | VERIFIED |

**Gaps:** no live ARPA 2026 hourly file; ARPA's near-real-time model is marked "temporarily unavailable"; no Tiber gauge API; no open tree census or noise map found.

### 3e. Mobility, traffic and transport

| Source | What you get | Access & licence | Status |
|---|---|---|---|
| [GTFS-RT vehicle positions](https://romamobilita.it/sites/default/files/rome_rtgtfs_vehicle_positions_feed.pb) | ~1,258 Atac + Roma TPL vehicles: trip, route, stop, odometer; refreshes every 30–60 s | No key; **CC BY-SA**; follow the 301 redirect | VERIFIED (decoded) |
| [GTFS-RT trip updates](https://romamobilita.it/sites/default/files/rome_rtgtfs_trip_updates_feed.pb) | Per-stop delay and uncertainty (watch outliers: one delay was 2,236 s) | CC BY-SA | VERIFIED |
| [GTFS-RT service alerts](https://romamobilita.it/sites/default/files/rome_rtgtfs_service_alerts_feed.pb) | 154 alerts: detours, cause, effect, Italian text | CC BY-SA | VERIFIED |
| [Static GTFS](https://romamobilita.it/sites/default/files/rome_static_gtfs.zip) | Schedule (46.6 MB zip, refreshed daily); calendar_dates only | CC BY-SA | VERIFIED |
| [Roma Mobilità GIS](https://data-rsm.opendata.arcgis.com/search?collection=dataset) | ZTL gates, traffic lights, bus lanes, cycle lanes, PGTU zones | Licence acceptance | Untested |
| [Cotral GTFS](https://www.cotralspa.it/open-data/) | Regional buses, Roma–Lido/Viterbo rail | Free | Untested (port 7777 blocked from the sandbox) |
| ViaggiaTreno (unofficial) / [Transitous](https://api.transitous.org/api/v1/geocode?text=roma%20termini) | Train delays / rail stations | Unofficial / community | Blocked (403) / VERIFIED geocode |
| [Bird Rome GBFS](https://mds.bird.co/gbfs/v2/public/rome/free_bike_status.json) | 4,101 e-scooters, 60 s TTL | Operator terms | VERIFIED |
| [Cooltra Rome GBFS](https://maas.zeus.cooltra.com/gbfs/rome/3.0/en/gbfs.json) | Mopeds | Check terms | Partial or stale (C=60) |
| [OpenSky](https://opensky-network.org/api/states/all?lamin=41.6&lomin=12.1&lamax=42.1&lomax=12.9), [adsb.lol](https://api.adsb.lol/v2/point/41.9/12.5/50), [adsb.fi](https://opendata.adsb.fi/api/v2/lat/41.9/lon/12.5/dist/50) | Aircraft | OpenSky: non-profit only | VERIFIED |
| [CCISS NAP](https://www.cciss.it/nap/mmtis/public/catalog/Dataset) | DATEX II road events, NeTEx | Unknown | Untested |
| Roma Mobilità loop sensors ([ITS page](https://romamobilita.it/sistemi-e-tecnologie/its-intelligent-transport-system/)) | 93 loop stations + 17 image sensors: flow, speed, occupancy, 5 min | Not public (C=70) | **Closed. Ask the PA** |
| TomTom / HERE traffic | Speed vs free-flow, incidents | Key; storage terms unread | TomTom endpoint alive (401) |
| [Waze for Cities](https://support.google.com/waze/partners/answer/10453062?hl=en) | Jams and closures | Public bodies only | Closed to the team |
| [CKAN parking](https://dati.comune.roma.it/catalog/api/3/action/package_show?id=atac-003) / [accidents 2022](https://dati.comune.roma.it/catalog/api/3/action/package_show?id=d108) | Paid-parking assets; accidents 2006–2022 | CC BY / CC BY-SA | VERIFIED metadata |

**Gaps:** no public live road-flow feed, no metro status feed, no parking occupancy, no ZTL gate status. Buses act as the only free live road probes.

### 3f. Crowd, activity and civic

| Source | What you get | Access & licence | Status |
|---|---|---|---|
| [DigitRoma Wi-Fi sessions](https://dati.comune.roma.it/catalog/api/3/action/package_show?id=wifi2026) | Daily anonymised sessions per hotspot, 2020–2026 | CC BY | VERIFIED metadata (check columns before storing) |
| [CzRM complaints 2026](https://dati.comune.roma.it/catalog/api/3/action/package_show?id=czrm-di-roma-capitale-dati-delle-segnalazioni-anno-2026) | Citizen reports by category | CC BY-SA; free text may hold personal data | VERIFIED metadata |
| [Roma CKAN catalogue](https://dati.comune.roma.it/catalog/api/3/action/package_list) | 365 datasets: 340 CC BY, 14 CC BY-SA, **11 non-commercial** | Free | VERIFIED |
| [Foursquare OS Places](https://docs.foursquare.com/data-products/docs/access-fsq-os-places) | 109M POIs, Oct 2026 release | Apache 2.0; token | Partial |
| [Meta population density](https://data.humdata.org/dataset/italy-high-resolution-population-density-maps-demographic-estimates) | ~30 m grid, frozen since 2024 | CC BY 4.0 | VERIFIED page |
| [BestTime](https://besttime.app/subscription/pricing) | Live venue busyness (0–100) | Paid | Untested |
| [Vodafone Analytics](https://grandiaziende.vodafone.it/analytics) / Motion Analytica | 200 m presence and OD, 2-day lag | Quote only | Closed to the team |
| [Strava Metro](https://metro.strava.com/terms) | Bike/walk counts | PA application; no redistribution | Closed to the team |

**Gap:** no free live crowd feed. Use daily Wi-Fi sessions plus scooter density as indirect activity signals.

### 3g. Video and webcams

| Source | What you get | Access & licence | Status |
|---|---|---|---|
| [Windy Webcams API](https://api.windy.com/webcams/pricing) | Webcam list and expiring image URLs | Free: link or embed only. Pro: €9,990 per year | Key (403 without) |
| [SkylineWebcams](https://www.skylinewebcams.com/en/terms-of-use.html) | Rome cams | **Forbids** recording, scraping and screenshots | Closed |
| [EarthCam](https://cc8.earthcam.net/eula/web) | Cams | **Forbids** capture and AI/ML use | Closed |
| YouTube live streams | Streams | [API ToS](https://developers.google.com/youtube/terms/api-services-terms-of-service?csw=1) grants no right to reproduce (C=70 that frame grabs are not allowed) | Closed |
| Roma Mobilità CCTV | Traffic cameras | Not public | Closed. PA edge counting only |

**Gap: no Rome webcam source permits storing or analysing frames.** The only lawful route is PA-owned cameras with edge counting, where the Comune is controller and runs a DPIA ([EDPB 3/2019](https://www.edpb.europa.eu/system/files/documents/files/file1/edpb_guidelines_201903_video_devices_en_0.pdf); [Garante FAQ](https://www.garanteprivacy.it/faq/videosorveglianza)). In the demo, embed only.

---

## 4. Paid options with prices

| Option | Price | What it unlocks | Recommendation |
|---|---|---|---|
| **Pléiades Neo 30 cm tri-stereo archive** ([Land Info](https://landinfo.com/satellite-imagery-pricing/)) | $55/km², 25 km² minimum ≈ **$1,375** (50 cm Pléiades ≈ $940) | True DSM (1–2 m class, C=70) → LoD2 roofs for the centre | **Buy only if** the catalogue shows a cloud-free Rome set, the EULA lets you publish derived geometry, and delivery fits the event |
| WorldView-3 stereo archive (Land Info) | $45/km² × 25 ≈ $1,125 | Stereo DSM | Alternative to the above |
| SkyFi 30 cm archive mono ([PDF](https://skyfi.com/files/SkyFi_Pricing_August_2025.pdf)) | $22.50–35/km², 5 km² minimum; a 15-date stack ≈ $1.7–2.6k | EOGS++ multi-date demo | Skip (research demo, not product) |
| SkyFi stereo / tri-stereo tasking | $60 / $90 per km² (30 cm), 25 km² min ≈ $1,500 / $2,250 | Fresh stereo | Skip (new capture; uncertain delivery) |
| SkyFi ready DSM | $215/km², 25 km² min ≈ $5,375 | DSM without processing | Skip (do s2p/ASP yourself) |
| [UP42](https://up42.com/pricing) | VHR archive from €6.80/km²; €100 minimum credits | Catalogue search and alternative supplier | Use to **check archive availability** |
| **Vexcel aerial via SkyFi** ([Vexcel Italy](https://vexceldata.com/countries/italy/)) | $35/km² (11–15 cm), $100–115/km² (7.5–10 cm), 1 km² min | Best geometric fidelity; oblique/DSM pricing via SkyFi unconfirmed (C=50) | Only if the licence allows open derived meshes (C=60 it is internal-use) |
| Google Photorealistic 3D Tiles ([pricing](https://developers.google.com/maps/billing-and-pricing/pricing)) | $6 per 1k (1k free/month) | Visual backdrop | Skip or backdrop only: [no 3D derivation, analysis or caching](https://developers.google.com/maps/documentation/tile/policies) |
| Google Solar API ([policies](https://developers.google.com/maps/documentation/solar/policies)) | Data Layers $75 per 1k (1k free); Building Insights $10 per 1k | 10 cm DSM for Italy | **Skip**: terms forbid "build 3D or terrain models" and export |
| Google Street View Static / Air Quality / Routes Pro | $7 / $5 / $10 per 1k (free 10k / 10k / 5k) | Images; AQ heatmap; traffic-aware routes | Skip. Routes cannot be used on non-Google maps and caches only 30 days ([terms](https://cloud.google.com/maps-platform/terms/maps-service-terms)) |
| [Cesium ion](https://cesium.com/pricing/) | Free Community; $149 / $499 per month | Hosting and tiling | Skip. Self-host 3D Tiles; a paid plan is needed for government use |
| [TomTom traffic](https://developer.tomtom.com/pricing) | Free 20k flow + 2.5k incidents per month; overage not verified | Live speed at sampled points | **Use the free tier** |
| [HERE traffic](https://www.here.com/get-started/pricing) | 5k free per month, then $2.75 per 1k | Flow plus jam factor | Optional second source |
| [Mapbox](https://www.mapbox.com/pricing) | Directions 100k free, then $2 per 1k; Traffic Data enterprise only | Traffic-aware routes | Skip |
| [BestTime](https://besttime.app/subscription/pricing) | $29/month (1,200 credits); $96/month for 50 venues | Landmark busyness | Buy Basic only if you do a crowd layer |
| Windy Webcams Pro | €9,990/year (C=85) | Full-size images, 24 h URLs; still no analysis right | Skip |
| **GPU: [Hyperstack](https://www.hyperstack.cloud/gpu-pricing)** | A6000 48 GB $0.50/h, L40 $1.00, A100 $1.35, H100 $2.50 | Splat training, Sionna district runs | **Use for heavy jobs** |
| **GPU: [Modal](https://modal.com/pricing)** | L4 $0.80/h, L40S $1.95, A100-80 $2.50, H100 $3.95; $30/month free credit; per-second billing | Serverless API plus burst GPU | **Use to host the tool API** |
| [Exa](https://exa.ai/pricing) | Free $10/month + $10 bonus; search $4/$7/$12 per 1k; agent run $0.012–1.00; Websets $49/month | Citations, dataset scouting, news monitors | Use free tier plus the hackathon credit (reportedly $1,000, C=60) |
| [ElevenLabs agents](https://elevenlabs.io/pricing/agents) | Free 15 min; Starter $6 (75 min); Creator $22 (275 min); $0.08/min extra | Voice agent | **Creator $22** |
| [Lovable](https://docs.lovable.dev/introduction/subscription-plans) | Free: 5 credits/day, no code edit or download; Pro $25/month | Front end | **Pro $25** (code edit plus download) |
| Avalanche C-Chain | Fuji free; mainnet median fee 0.0000047 AVAX ([benchmark](https://www.avalanche.com/about/blog/the-price-of-a-transaction-benchmarking-the-avalanche-c-chain-on-cost-and-capture/)) | Hash anchoring | Use Fuji |

**Tier totals [inf]:**

| Tier | Contents | Total |
|---|---|---|
| Zero-euro | 4060 Ti; Modal $30 free credit; free tiers of Lovable, ElevenLabs (15 min), Exa, TomTom and HERE; Fuji | **$0** |
| Lean | GPU budget cap $150 + Lovable Pro $25 + ElevenLabs Creator $22 + BestTime $29 | **≈ $226** |
| **Recommended** | Lean + Pléiades Neo tri-stereo 25 km² ($1,375) | **≈ $1,600** |
| Recommended + aerial hero tile | + Vexcel 7.5 cm, 2 km² (≈$230), licence permitting | ≈ $1,830 |

Data purchases dominate the budget. GPU compute is cheap by comparison (C=80 [inf]).

---

## 5. Reconstruction plan that is valid on your compute

| Product | Method | Where it runs |
|---|---|---|
| **LoD1 for all of Rome** | Overture/OSM footprints + GlobalBuildingAtlas heights (fallback: levels × ~3.2 m); terrain from TINITALY/GLO-30; export to CityJSON + 3D Tiles (3dfier or a script) | 4060 Ti / CPU (C=80) |
| **Landmark splats** (Pantheon, Forum, Navona, Vittoriano, St Peter's) | Start from MegaScenes COLMAP poses (no SfM cost). Blur faces. Train gsplat/splatfacto on 200–400 downscaled images | 4060 Ti (C=65 [bg]) |
| In-the-wild splats (lighting changes, tourists) | WildGaussians-style transient masking | Rented A100/H100 (24–80 GB, C=65 [bg]) |
| Few-photo feed-forward | VGGT (8 GB ≈ 30 frames; commercial weights exclude military use, [HF](https://huggingface.co/facebook/VGGT-1B-Commercial)), MapAnything | 4060 Ti ≤30 frames; rented above that |
| Street corridors | Mapillary images with computed geo-poses | 4060 Ti |
| **True DSM → LoD2** (optional purchase) | Tri-stereo → s2p (AGPL) or NASA ASP (Apache 2.0) → DSM → roofer/geoflow with OSM footprints | Rented CPU/GPU (C=70 [bg]) |
| Satellite multi-date (optional) | [EOGS++](https://github.com/gardiens/EOGS2) (building MAE 1.19 m on benchmarks, [ISPRS](https://isprs-annals.copernicus.org/articles/XI-2-2026/217/2026/)) | Rented A100 |

**Georeferencing.** Fit a Sim(3) with COLMAP `model_aligner` using GPS EXIF where present. Many Wikimedia photos lack GPS (C=60 [bg]). Otherwise register Mapillary images into the model, or click 6–12 control points on the AGEA 20 cm orthophoto and on LoD1 building corners. **Never** register to Google tiles.

**Delivery.** Serve splats as 3D Tiles with `KHR_gaussian_splatting` + SPZ, which CesiumJS 1.139 supports. Ratification status is unclear ([RadianceFields](https://radiancefields.com/cesium-adds-hierarchical-lod-for-gaussian-splats-to-3d-tiles-cesiumjs-and-cesium-for-unreal)). deck.gl/MapLibre have no official splat layer (C=55). So use CesiumJS for the 3D view.

**Honest validation metrics [inf, C=75]:**

| Product | Metric | Reference |
|---|---|---|
| LoD1 heights | MAE, bias and RMSE per building; % of buildings with any height | Urban Atlas BH 2012 at building centroids (itself 10 m, 2012: flag the vintage) |
| DSM / LoD2 | Height MAE and NMAD; roof-plane fit residual | LoD1, Urban Atlas, a few known landmark heights |
| Splats | PSNR, SSIM, LPIPS on **held-out views** (e.g. every 8th image); COLMAP mean reprojection error (≈ sub-pixel is typical, C=70 [bg]) | Images withheld from training |
| Georeferencing | Residual in metres at control points not used in the fit | AGEA ortho, cadastral WMS |

Publish the metric table in the UI next to each layer. Multi-view note: landmark reconstruction from many tourist photos **is** multi-view geometry in practice, and the natural place for your expertise. Nothing else in the plan depends on it.

---

## 6. Dynamic layer, probabilistic core and architecture

**Belief layers [inf, C=75].** Use one common grid (H3 or 100 m). Each cell stores a mean, a variance and a timestamp. The prior comes from a model. Observations update it, each with its own noise. Variance grows when no data arrives. This is the twin-as-probabilistic-model pattern ([Kapteyn et al.](https://www.nature.com/articles/s43588-021-00069-0)). Kriging with model drift cut NO2 RMSE by 48% in Barcelona ([Criado et al.](https://gmd.copernicus.org/articles/16/2193/2023/)).

| Belief layer | Prior | Live updates (feed cadence) |
|---|---|---|
| Transit delay / bus speed | Static GTFS schedule | GTFS-RT positions + trip updates (30–60 s) |
| Road speed | SUMO free-flow / OSM speed limits | Bus probes (odometer), TomTom/HERE sampled points |
| Disruptions | — | GTFS-RT alerts; Exa news monitors (text sensor, geocoded, with confidence) |
| Air quality (NO2, PM) | Open-Meteo/CAMS 10 km | EEA hourly stations (13 NO2 points), Sensor.Community (minutes) |
| Rain / flood alert | ECMWF / Open-Meteo forecast | DPC radar (5 min), DPC daily bulletins |
| Heat | ERA5 / forecast | Landsat and ECOSTRESS LST when a scene arrives |
| Land cover / change | WorldCover 2021 | Sentinel-2 scenes (every few days) |
| Activity | Population grid + POIs | Wi-Fi sessions (daily), Bird GBFS (60 s), BestTime (if bought) |
| EMF | Free-space / Sionna prior from estimated sites | No live feed. A few ARPA points typed in from PDFs; **wide band labelled "uncalibrated"** |

**Architecture [inf, C=75]:**

| Layer | Choice |
|---|---|
| Storage | PostGIS + TimescaleDB, or DuckDB + GeoParquet for a serverless demo. Entities shaped as NGSI-LD / Smart Data Models so a broker can be added later ([EU LDT blueprint](https://spec.knows.idlab.ugent.be/ldt-interoperability-blueprint/latest/)) |
| Ingest | Cron workers: GTFS-RT archiver, EEA puller, radar puller, Exa monitors. Every snapshot is hashed |
| Tool API | FastAPI on Modal: `context_check`, `estimate_field`, `run_traffic_scenario`, `query_layer`, `legal_lookup`. Strict JSON schemas |
| Simulation | SUMO (CPU) and Sionna RT (GPU) workers |
| Front end | Lovable React app; CesiumJS for 3D/splats; MapLibre for 2D |
| Agents | One orchestrator calling tools; Exa for web; the ElevenLabs voice agent calls the same API |
| Provenance | Hash table + Avalanche Fuji anchor contract |

---

## 7. Scenario simulation

**Traffic (real network, synthetic demand) [inf, C=75].** SUMO on a bounded district, driven through the open [SUMO-MCP-Server](https://github.com/XRDS76354/SUMO-MCP-Server) (network build, demand, signals, TraCI control). Precedents to copy: [AgentSUMO](https://arxiv.org/abs/2511.06804) (clarify-before-execute), [SUMO_LLM_Agent](https://github.com/xuyimingxym/SUMO_LLM_Agent) and [ChatSUMO](https://www.sciencedirect.com/science/article/abs/pii/S0968090X26002470).

- Network: OSM or the ready [Mobility Sim Lab Rome net](https://www.mobilitysimlab.com/rome-maps/) (licence unknown).
- Buses: from static GTFS.
- Demand: **no open calibrated Rome demand exists**. Label it in three tiers: random/activity-based (uncalibrated) → routeSampler against loop counts (only if the PA shares them) → speed check against GTFS-RT bus probes and TomTom.
- Do not promise micro-simulation of the whole city; even Turin's 600 km² model is mesoscopic ([SUMO scenarios](https://sumo.dlr.de/docs/Data/Scenarios.html)).
- KPIs: travel time, delay, queues, bus delay, CO2/NOx (HBEFA).

**Antenna / EMF (physics real, inputs assumed).**

- Prior: free space, E ≈ √(30·EIRP)/d, root-sum-square across sources. EIRP, tilt and azimuth are assumptions (C=55).
- Ray tracing: [Sionna RT](https://nvlabs.github.io/sionna/rt/tutorials/Radio-Maps.html) `RadioMapSolver` on an OSM/LoD1 scene. Turn diffraction ON, or buildings cast false total shadows ([docs](https://propagamap.github.io/sionna-rt/tutorials/Diffraction.html)).
- Compute: a 300 m context at 2–5 m cells is plausible on 8 GB (C=55). A district runs on a rented L4/L40S, the class the maintainers suggest ([discussion](https://github.com/NVlabs/sionna/discussions/971)).
- Accuracy: even the best validated EIRP ray tracing shows **1.6–3.8 dB median deviation and can underestimate** ([IEEE 2026](https://ieeexplore.ieee.org/document/11479602)). So return **P5/P50/P95 in V/m**, and P(E > 15 V/m) computed by code against the config threshold.
- "Add or move an antenna" = baseline run vs variant run → a delta map.

**Other scenarios, ranked by data availability [inf, C=55]:**

| Rank | Scenario | Real vs synthetic |
|---|---|---|
| 1 | Accessibility / 15-minute city (r5py + GTFS + OSM) | Real inputs |
| 2 | Antenna viewshed / visual impact (DEM + LoD1/LoD2) | Real geometry |
| 3 | Shadow / solar on LoD1 or LoD2 | Real geometry, approximate heights |
| 4 | Noise ([NoiseModelling](https://noise-planet.org/noisemodelling.html), CNOSSOS-EU, fed by SUMO) | Real roads, synthetic volumes |
| 5 | Population exposure (ISTAT sections × field or noise maps) | Real aggregates |
| 6 | Air quality | Show the belief layer; do not simulate dispersion |
| 7 | Tiber flood | Show IdroGEO / official hazard layers; do not simulate |
| 8 | Pedestrian crowds | Skip (no geometry or counts) |

---

## 8. Antenna challenge mapping

| Challenge requirement | Data source | Status |
|---|---|---|
| Geolocated installation database | OpenCelliD centroids clustered into estimated sites (eNB = cell >> 8, DBSCAN 150–300 m, C=70 heuristic) + OSM masts + beaconDB | **Crowd-sourced / estimated, not official.** CC BY-SA |
| Authorisation status, technical data | None public | **Synthetic placeholder**, clearly labelled. FOIA (accesso civico generalizzato) to Roma Capitale SUET/Urbanistica and ARPA Lazio |
| EMF maps | Own prior + Sionna, with ranges | Model estimate. Cartoradio is **link-out only** (legal notes) |
| Measurement points | ARPA Lazio PDFs (Boncompagni) | Typed in by hand; ask ARPA via FOIA for the point dataset |
| 300 m: schools | Roma GeoServer 916 + 390 + 333 | VERIFIED official |
| 300 m: hospitals | Roma `DIPAMB:Ospedali` (38) + OSM | VERIFIED, incomplete |
| 300 m: RSA | OSM `nursing_home` + geocoded Lazio accredited list | No official layer (C=70) |
| 300 m: playgrounds | OSM `leisure=playground` | No official layer |
| Landscape constraints | Lazio PTPR A/B, SITAP art. 136/142, Vincoli in Rete (WMS), UNESCO | VERIFIED |
| Rete Ecologica | `DIPAU:ReteEcologicaPoligono` | VERIFIED |
| Carta per la Qualità | `DIPAU:CartaPerLaQualita_*` | VERIFIED |
| Natura 2000 | Lazio `geonode:rete_natura200000` | VERIFIED |
| Legal basis | [D.Lgs. 259/2003](https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2003-08-01;259), [L. 36/2001](https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2001-02-22;36), L. 214/2023 | VERIFIED URLs |

**Present distance checks as information, not a ban.** In 2021 the Consiglio di Stato struck down Rome's 2015 rule banning antennas within 100 m of sensitive sites as a generalised ban ([MondoMobileWeb](https://www.mondomobileweb.it/?p=194798)) (C=80). Implement the check in PostGIS/geometry code, never in the LLM.

---

## 9. Sponsor fit

| Sponsor | Meaningful role | Key facts |
|---|---|---|
| **Lovable** | Whole front end: map, chat, scenario cards, "Verify" page. Edge functions hold all keys and proxy to the Modal API | React/Supabase; Git sync on every plan; code edit and download need Pro ([docs](https://docs.lovable.dev/introduction/subscription-plans)). Judging criteria unknown (C=40): keep the Lovable commit history visible |
| **Exa** | (1) `legal_lookup` restricted to normattiva, gazzettaufficiale, agid, garanteprivacy, arpalazio, returning URL + timestamp. (2) Dataset-scout Agent with structured output: publisher, licence, cadence. (3) **Monitors** for roadworks, strikes and demonstrations as a geocoded "text sensor" | Agent API with field-level grounding; MCP at `mcp.exa.ai/mcp`; 5–10 QPS limits ([pricing](https://exa.ai/docs/admin/pricing), [agent](https://exa.ai/docs/agent/overview)) |
| **ElevenLabs** | Voice briefing for officers ("what changed in Municipio I today?") and a citizen hotline. One webhook tool `ask_twin` shares the backend and guardrails. Language-detection tool for IT/EN; transfer tool hands off to a human office | Guardrails 2.0: focus, prompt-injection detection, custom validators; tool-call and simulation tests ([guardrails](https://elevenlabs.io/docs/eleven-agents/best-practices/guardrails), [testing](https://elevenlabs.io/docs/eleven-agents/customization/agent-testing)). Italian quality not verified |
| **Avalanche / team1** | `anchor(bytes32 root, kind, uri)` event on **Fuji** (chain 43113) for dataset snapshots, simulation runs (inputs, code commit, outputs) and agent reports. A "Verify" page re-hashes a report. **No personal data on-chain** | [Fuji RPC](https://docs.avax.network/docs/rpcs/c-chain); fees ([docs](https://docs.avax.network/docs/rpcs/other/guides/txn-fees)). An anchor is evidence, not an eIDAS qualified timestamp (C=65 [bg]) |

---

## 10. Guardrails

**Regulation:**

| Rule | What it requires |
|---|---|
| AI Act art. 50 (applies since 2 Aug 2026) | Tell users they are talking to AI, in chat and in the first voice line; label AI-generated public-interest text ([EC FAQ](https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act)). High-risk Annex III is delayed to 2 Dec 2027 ([omnibus](https://www.regulation-ai.eu/en/omnibus/)) |
| Legge 132/2025 art. 14 | AI in the PA is "instrumental and supportive"; the human official stays solely responsible ([Conferenza Stato-Città](https://www.conferenzastatocitta.gov.it/home/approfondimenti/tematiche-di-interesse/l-intelligenza-artificiale-ia-nella-pa/la-normativa-italiana-la-legge-1322025/)) |
| AgID guidelines, 9 Nov 2026 (Det. 169) | Classify by AI Act risk; human oversight; PDCA / ISO 42001; AI-specific cybersecurity; final responsibility stays with the PA ([PDF](https://www.agid.gov.it/sites/agid/files/2026-11/Linee_guida_Adozione_IA_nella_PA.pdf)) |
| GDPR / Garante | Video counting is still personal-data processing ([AP NL](https://www.autoriteitpersoonsgegevens.nl/en/themes/camera-surveillance/camera-surveillance-in-public-places/cameras-in-advertising-panels)) |

Classification: decision support, not automated decisions, is most plausibly **not high-risk** (C=65, not legal advice). Avoid scoring permit applications.

**Technical design** ([OWASP LLM 2026](https://genai.owasp.org/download/56857/), [MCP cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html)) [inf, C=80]:

- Deterministic tools do geometry, thresholds and 300 m checks. The LLM never computes or recalls legal numbers.
- Answer contract: every claim carries a source ID (dataset hash, Exa URL + timestamp, or run ID). Otherwise the answer is "insufficient data".
- Uncertainty is always shown as range + method + validation status. Synthetic data is always labelled.
- Role tiers (citizen vs office) are enforced in the API and row-level security, not in the prompt.
- Exa and web content enter as quoted, provenance-tagged data. No side-effect tool is reachable in the same turn as untrusted content (Rule of Two). Strip invisible Unicode.
- Strict JSON schemas (`additionalProperties:false`); pinned tool definitions; human approval before any externally visible action.
- PII filter on inputs and logs: addresses reduced to street or block level; short transcript retention.
- Full audit log, with hashes anchored on-chain. An eval set covers grounding, refusal, injection and IT/EN voice.

---

## 11. Licence and privacy risks

| Item | Risk | Action |
|---|---|---|
| OSM, Overture (ODbL); GTFS + GTFS-RT, Mapillary, OpenCelliD, CzRM (CC BY-SA) | **Share-alike** on derived databases | Publish derived layers under ODbL / CC BY-SA; keep an attribution manifest (C=70 on the reach of share-alike) |
| 11 non-commercial CKAN datasets | Conflict with an open licence | Exclude them |
| Google 3D Tiles / Solar / Routes | No 3D derivation, export, caching or non-Google maps | Backdrop only, or skip; never commit keys or tiles |
| VHR / Vexcel EULAs | Raw imagery not publishable (C=75) | Publish derived geometry only, after reading the clause |
| MegaScenes / Wikimedia photos | Per-photo CC licences; faces | Blur before training; publish splats with attribution; never raw photos |
| Cartoradio COG | Reuse forbidden by its legal notes | Link out; ask cartoradio@fub.it in writing |
| Webcams | **No Rome source permits storing or analysing frames** | Embed only; PA cameras with edge counting under the Comune's DPIA |
| OpenSky | Non-profit only | Fine for the demo; flag for PA operation |
| Roma `241_ServiziSanitarieAssistenziali` | Fields **ref-nome, ref-cell, telefono, e-mail** | Drop them at ingest |
| Accidents, CzRM free text, Wi-Fi CSV | Possible personal data (C=55) | Inspect columns; aggregate; drop free text |
| Voice / chat inputs | Accidental addresses and names | PII filter; no storage on-chain |
| GeoServer layers | No licence stated (C=60 CC BY) | Credit "Roma Capitale – GeoPortale"; check the Note legali |

---

## 12. Build order with gates

1. **Gate 0, decide:** hero district, spend tier, whether to request the stereo quote (section 13). Create the public repo, licence file and data manifest (source, licence, hash, verified flag).
2. Ingest the static layers: Overture/OSM buildings, Roma and Lazio GeoServer context layers, SITAP, ISTAT, OpenCelliD (PMTiles or token), Natura 2000. Drop personal fields.
   - **Gate A:** every layer loads in DuckDB/PostGIS with a hash. **No-go:** a layer fails → mark it "not available" in the UI and move on.
3. LoD1 for all of Rome → 3D Tiles; validate heights against Urban Atlas.
   - **Gate B:** renders in CesiumJS inside the Lovable app on the demo laptop. **No-go:** fall back to a MapLibre extrusion.
4. Deterministic tools: `context_check(300 m)` and the EMF prior with P5/P50/P95 and the threshold config.
   - **Gate C:** three scripted addresses give correct counts against a manual GIS check.
5. Live ingest: GTFS-RT archiver, EEA, DPC radar, Open-Meteo, Bird; belief layers with variance.
   - **Gate D:** layers update and show timestamps and uncertainty. **No-go:** freeze to the last cached snapshot, labelled.
6. Agent + Exa `legal_lookup` + cited report; Avalanche anchoring of snapshots and reports.
   - **Gate E:** end-to-end report with sources and an on-chain hash that the Verify page checks. **Go:** this is the demo-safe core.
7. Scenarios: SUMO closure what-if via the MCP server; Sionna on one 300 m context (GPU).
   - **Gate F:** baseline vs variant deltas render with "synthetic demand" / "assumed EIRP" labels. **No-go:** keep the free-space prior only.
8. Landmark splats from MegaScenes (4060 Ti first; rented A100 if needed); georeference; held-out metrics.
   - **Gate G:** georeferencing residual and held-out PSNR shown in the UI. **No-go:** show LoD1 only.
9. ElevenLabs voice agent on the same API, with guardrails and tool-call tests.
10. Optional: tri-stereo DSM → LoD2, only if bought and delivered.
11. Freeze, cache an offline fallback, record a backup video.

---

## 13. Open questions and suggestions

1. **Budget ceiling for paid data?** Zero, ≈$230 or ≈$1.6k changes step 10.
2. **Buy a stereo pair?** First check UP42/OneAtlas for a cloud-free Pléiades Neo tri-stereo set over the centre, the EULA derived-data clause and delivery speed. If any of the three fails, skip it.
3. **Is someone from Roma Capitale or Roma Mobilità at the event?** Ask for loop-sensor data, the antenna/SUET list (even a sample), and the GeoServer licence. Any of these upgrades a synthetic layer to a real one.
4. **OpenCelliD token:** register now. Otherwise use the 2025 PMTiles mirror.
5. **Hero district [inf]:** Centro Storico / UNESCO area plus Villa Borghese–Flaminio. It has MegaScenes landmarks, dense context layers, a Natura 2000 site and heavy bus traffic. Alternative: Prati.
6. **Avalanche wallet:** do you have one with Fuji test AVAX? (Faucet limits not checked.)
7. **Exa hackathon credit:** confirm how it is delivered and whether it covers Monitors and Agent runs.
8. **Google key:** only for a backdrop. Skipping it removes a whole class of licence risk.
9. **ElevenLabs Italian voice:** test latency and quality early. It was not verified.

---

## Sources

**Antenna, EMF, law:** [Roma GeoPortale servizi](https://geoportale.comune.roma.it/servizi/) · [Roma WFS caps](https://geoportale.comune.roma.it/geoserver/ows?service=WFS&version=1.0.0&request=GetCapabilities) · [Lazio WFS caps](https://geoportale.regione.lazio.it/geoserver/ows?service=WFS&version=1.0.0&request=GetCapabilities) · [SITAP](https://sitap.cultura.gov.it/geoserver/ows) · [Vincoli in Rete](http://vincoliinrete.beniculturali.it/geoserver/ows) · [EEA Natura 2000](https://bio.discomap.eea.europa.eu/arcgis/rest/services/ProtectedSites/Natura2000Sites/MapServer?f=json) · [OpenCelliD](https://opencellid.org/downloads.php) · [OpenCelliD format](https://wiki.opencellid.org/wiki/Database_format) · [Source Cooperative mirror](https://source.coop/smartmaps/opencellid) · [beaconDB](https://beacondb.net/) · [cartoradio map](https://www.cartoradio.it/map) · [cartoradio legal notes](https://www.cartoradio.it/note-legali) · [ARPA Lazio Boncompagni](https://www.arpalazio.it/documents/20124/154891/Monitoraggio+CEM+Boncompagni+202110.pdf) · [ARPA Lazio sites 2018](https://www.arpalazio.it/documents/20124/51651/Impianti_RF_CEM_2018.pdf) · [ARPA Lazio sites 2024](https://www.arpalazio.it/documents/20124/51651/IMPIANTI_RF_CEM_2024.pdf) · [MIMIT FAQ 2024](https://www.mise.gov.it/images/stories/documenti/FAQ_2024_campi_elettromagnetici_CCE.pdf) · [ARPAE/AIRP](https://aggiornati.arpae.it/it/notizie/notari-convegno-airp-contributo.pdf) · [DPCM 8/7/2003 text](https://www.arpacampania.it/documents/20182/261099/06.+DPCM+8+luglio+2003+protezione+pubblico+campi+a+radiofrequenza.pdf/e8b8c373-6354-4234-80da-3c624f422bd8) · [L. 214/2023](https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2023-12-30;214) · [L. 36/2001](https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2001-02-22;36) · [D.Lgs. 259/2003](https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2003-08-01;259) · [MIMIT decree 30 Jul 2026](https://www.mimit.gov.it/it/normativa/decreti-interministeriali/decreto-interministeriale-30-luglio-2026-nuovi-limiti-di-esposizione-ai-campi-elettromagnetici) · [CdS 2021 (MondoMobileWeb)](https://www.mondomobileweb.it/?p=194798) · [Infratel map news](https://www.tuttoandroid.net/news/2026/01/20/infratel-mappa-interattiva-copertura-reti-mobili-4g-5g-1136189/) · [IEEE EMF ray tracing](https://ieeexplore.ieee.org/document/11479602) · [Sionna radio maps](https://nvlabs.github.io/sionna/rt/tutorials/Radio-Maps.html) · [Sionna diffraction](https://propagamap.github.io/sionna-rt/tutorials/Diffraction.html) · [Sionna VRAM discussion](https://github.com/NVlabs/sionna/discussions/971)

**3D and imagery:** [SkyFi price PDF](https://skyfi.com/files/SkyFi_Pricing_August_2025.pdf) · [SkyFi pricing](https://www.skyfi.com/pricing) · [Land Info](https://landinfo.com/satellite-imagery-pricing/) · [UP42](https://up42.com/pricing) · [Vexcel Italy](https://vexceldata.com/countries/italy/) · [Google Maps pricing](https://developers.google.com/maps/billing-and-pricing/pricing) · [Solar policies](https://developers.google.com/maps/documentation/solar/policies) · [Tiles policies](https://developers.google.com/maps/documentation/tile/policies) · [Cesium pricing](https://cesium.com/pricing/) · [MegaScenes](https://registry.opendata.aws/megascenes/) · [MegaScenes paper](https://arxiv.org/pdf/2406.11819) · [Mapillary licences](https://help.mapillary.com/hc/en-us/articles/115001770409-Licenses) · [Urban Atlas BH](https://land.copernicus.eu/local/urban-atlas/building-height-2012) · [GlobalBuildingAtlas](https://un-spider.org/news-and-events/news/globalbuildingatlas-open-global-3d-buildings-data-digital-twins-and-disaster) · [Overture](https://docs.overturemaps.org/guides/buildings) · [EOGS++](https://github.com/gardiens/EOGS2) · [VGGT commercial](https://huggingface.co/facebook/VGGT-1B-Commercial) · [MapAnything](https://arxiv.org/html/2509.13414v1) · [Cesium splat HLOD](https://radiancefields.com/cesium-adds-hierarchical-lod-for-gaussian-splats-to-3d-tiles-cesiumjs-and-cesium-for-unreal) · [EarthView](https://arxiv.org/html/2501.08111v1) · [Umbra](https://registry.opendata.aws/umbra-open-data/)

**Environment:** [EEA AQ API](https://eeadmz1-downloads-api-appservice.azurewebsites.net/swagger/index.html) · [ARPA chimici](https://www.arpalazio.net/main/aria/sci/basedati/chimici/chimici.php) · [Open-Meteo pricing](https://open-meteo.com/en/pricing) · [CAMS ADS](https://ads.atmosphere.copernicus.eu/api/catalogue/v1/collections/cams-europe-air-quality-forecasts) · [DPC radar docs](https://dpc-radar.readthedocs.io/it/radar_v2/api.html) · [CDSE quotas](https://documentation.dataspace.copernicus.eu/Quotas.html) · [OpenAQ limits](https://docs.openaq.org/using-the-api/rate-limits) · [IQAir API](https://www.iqair.com/air-pollution-data-api) · [GEE tiers](https://developers.google.com/earth-engine/guides/noncommercial_tiers) · [IdroGEO](https://idrogeo.isprambiente.it/api/pir/comuni/058091) · [EGMS](https://egms.land.copernicus.eu/)

**Mobility, crowd, video:** [Roma Mobilità open data](https://romamobilita.it/sistemi-e-tecnologie/open-data/) · [ITS page](https://romamobilita.it/sistemi-e-tecnologie/its-intelligent-transport-system/) · [Centrale mobilità](https://romamobilita.it/sistemi-e-tecnologie/centrale-mobilita/) · [CKAN catalogue](https://dati.comune.roma.it/catalog/api/3/action/package_search?rows=400&sort=metadata_modified+desc) · [MobilityData GBFS systems](https://raw.githubusercontent.com/MobilityData/gbfs/master/systems.csv) · [TomTom pricing](https://developer.tomtom.com/pricing) · [HERE pricing](https://www.here.com/get-started/pricing) · [Mapbox pricing](https://www.mapbox.com/pricing) · [Google Maps service terms](https://cloud.google.com/maps-platform/terms/maps-service-terms) · [BestTime pricing](https://besttime.app/subscription/pricing) · [Vodafone Analytics](https://grandiaziende.vodafone.it/analytics) · [Strava Metro terms](https://metro.strava.com/terms) · [Windy pricing](https://api.windy.com/webcams/pricing) · [SkylineWebcams terms](https://www.skylinewebcams.com/en/terms-of-use.html) · [EarthCam EULA](https://cc8.earthcam.net/eula/web) · [EDPB 3/2019](https://www.edpb.europa.eu/system/files/documents/files/file1/edpb_guidelines_201903_video_devices_en_0.pdf) · [Garante FAQ](https://www.garanteprivacy.it/faq/videosorveglianza)

**Simulation, sponsors, guardrails:** [SUMO-MCP-Server](https://github.com/XRDS76354/SUMO-MCP-Server) · [AgentSUMO](https://arxiv.org/abs/2511.06804) · [SUMO_LLM_Agent](https://github.com/xuyimingxym/SUMO_LLM_Agent) · [ChatSUMO](https://www.sciencedirect.com/science/article/abs/pii/S0968090X26002470) · [Mobility Sim Lab Rome](https://www.mobilitysimlab.com/rome-maps/) · [SUMO scenarios](https://sumo.dlr.de/docs/Data/Scenarios.html) · [NoiseModelling](https://noise-planet.org/noisemodelling.html) · [EU LDT blueprint](https://spec.knows.idlab.ugent.be/ldt-interoperability-blueprint/latest/) · [Kapteyn et al.](https://www.nature.com/articles/s43588-021-00069-0) · [Criado et al.](https://gmd.copernicus.org/articles/16/2193/2023/) · [Lovable plans](https://docs.lovable.dev/introduction/subscription-plans) · [Lovable Supabase](https://docs.lovable.dev/integrations/supabase) · [Exa pricing](https://exa.ai/docs/admin/pricing) · [Exa agent](https://exa.ai/docs/agent/overview) · [Exa MCP](https://exa.ai/docs/reference/exa-mcp) · [ElevenLabs agent pricing](https://elevenlabs.io/pricing/agents) · [ElevenLabs guardrails](https://elevenlabs.io/docs/eleven-agents/best-practices/guardrails) · [ElevenLabs testing](https://elevenlabs.io/docs/eleven-agents/customization/agent-testing) · [Avalanche C-Chain RPC](https://docs.avax.network/docs/rpcs/c-chain) · [Avalanche fees](https://docs.avax.network/docs/rpcs/other/guides/txn-fees) · [Avalanche fee benchmark](https://www.avalanche.com/about/blog/the-price-of-a-transaction-benchmarking-the-avalanche-c-chain-on-cost-and-capture/) · [Modal pricing](https://modal.com/pricing) · [Hyperstack pricing](https://www.hyperstack.cloud/gpu-pricing) · [AI Act art. 50 FAQ](https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act) · [Digital omnibus](https://www.regulation-ai.eu/en/omnibus/) · [L. 132/2025](https://www.conferenzastatocitta.gov.it/home/approfondimenti/tematiche-di-interesse/l-intelligenza-artificiale-ia-nella-pa/la-normativa-italiana-la-legge-1322025/) · [AgID guidelines](https://www.agid.gov.it/sites/agid/files/2026-11/Linee_guida_Adozione_IA_nella_PA.pdf) · [OWASP LLM 2026](https://genai.owasp.org/download/56857/) · [OWASP MCP](https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html)
