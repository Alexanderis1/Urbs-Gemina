# Rome stereo / tri-stereo VHR archive check (central Rome, lon 12.44-12.53, lat 41.87-41.93), as of 13 Nov 2026

Box size for reference: about 7.5 km x 6.7 km, about 50 km² (my own arithmetic from the coordinates).

Method note: I queried public catalogue APIs with curl from a cloud sandbox. Results:
- ESA EO-CAT (eocat.esa.int): connection reset by the sandbox network proxy every time; WebFetch refused it (robots). FEDEO (fedeo.ceos.org) answered, but its granule searches for ESA archive collections are passed on to the EO-CAT backend and returned HTTP 400. **Not checked.**
- Copernicus Data Space STAC (stac.dataspace.copernicus.eu), collection `ccm-optical`: **queried, results below (VERIFIED).**
- Airbus OneAtlas search API: HTTP 401 (needs an API key). Airbus GeoStore / DINAMIS: proxy 502. Apollo Image Hunter: Cloudflare challenge on the web app; its API (imagehunter-api.apollomapping.com/ajax/search) returns 401 "Missing Authorization Header". SkyFi platform API: 401 "Use 'X-Skyfi-Api-Key' header". Arlula: "Invalid Authorization Header". UP42 catalogue: needs an account. **No commercial catalogue could be searched without logging in.**
- MASE LiDAR WMS (wms.pcn.minambiente.it): **queried and rendered over the box (VERIFIED, see last section).**

## Q1. Does a Pléiades / Pléiades Neo stereo or tri-stereo archive set over central Rome exist?

### Takeaway
UNKNOWN: no catalogue record of a Pléiades stereo or tri-stereo set over Rome could be seen without a login. VERIFIED: the Airbus archive holds many single cloud-free Pléiades and Pléiades Neo scenes of central Rome. A stereo set of a European capital is likely but not proven (confidence 55). Even if one exists, UP42 and Airbus do not sell catalogue stereo self-service. It is "upon request", so a sales contact is needed.

### Cited Findings
- VERIFIED catalogue records (Copernicus Contributing Missions optical collection, CDSE STAC search with the bbox above, 17 items). Each is a single acquisition (one timestamp per date), so none is a stereo set. Records: Pléiades Neo 3 `PN03_PNE_MS2__3_20240630T100752_..._daca` (30 Jun 2024, cloud 0%, incidence 3.39°); Pléiades 1B `PH1B_PHR_MS___3_20200712T100837_..._c3cb` (12 Jul 2020, 0%, incidence 3.02°); Pléiades 1A `PH1A_PHR_MS___3_20180618T101619_..._61ed` (18 Jun 2018, 0%, incidence 15.45°); GeoEye-1 `GY01_GIS_MS4_OR_20210705T100534_..._2e04` (5 Jul 2021, 0%, incidence 4.61°); GEOSAT-2 `DM02_HRS_MS2_1D_20240629T0838..` (29 Jun 2024, 0%, 5.41°); Vision-1 `VS01_S14_MS2__3_20240801T084259_...` (1 Aug 2024, 0%, 10.21°). These are Copernicus-service data, not for sale through this route. — [CDSE STAC search endpoint](https://stac.dataspace.copernicus.eu/v1/search) (POST, collections=["ccm-optical"], bbox=[12.44,41.87,12.53,41.93]); collection described at [FEDEO ccm-optical](https://fedeo.ceos.org/collections/ccm-optical?httpAccept=application/geo%2Bjson)
- A Pléiades Neo image of Rome's historic centre exists from 28 March 2023 (ESA "Earth from Space"). It is mono as far as stated. — [ESA Earth from Space: Rome](https://www.esa.int/media/earth-from-space-rome-italy-en-377966)
- UP42 Pléiades and Pléiades Neo: catalogue acquisition modes are "Mono, Stereo*, Tri-stereo*" where * = "Upon request". Primary (sensor geometry, with RPC) products are also "upon request" / "non-integrated". Pléiades catalogue costs from 1,000 credits/km² and Pléiades Neo from 1,800 credits/km². — [UP42 Pléiades](https://docs.up42.com/data/pleiades); [UP42 Pléiades Neo](https://docs.up42.com/data/pleiades-neo)
- UP42 minimum charge for non-integrated Pléiades / Pléiades Neo catalogue products is 25 km². Integrated products have a "10 minutes" tier (0.1 km² minimum) and a "few days" tier (1 or 5 km²). — [UP42 minimum charges](https://docs.up42.com/data/catalog-min-charges)
- Apollo Mapping list prices (price list modified 8 Jul 2025), archive with a 25 km² minimum: Pléiades 1 stereo $25/km²; Pléiades 1 tri-stereo $37.50/km²; Pléiades Neo stereo $42.50/km²; Pléiades Neo tri-stereo $55/km². — [Apollo Mapping price list PDF](https://apollomapping.com/image_downloads/Apollo_Mapping_Imagery_Price_List.pdf)
- Apollo academic discount: Pléiades 1 / Pléiades Neo / SPOT 50% off; WorldView / GeoEye 30% off. The same note says a $5,000 archive minimum applies. From the layout of the PDF it is unclear whether that minimum covers all discounts or only the Planet line. — [Apollo price list PDF](https://apollomapping.com/image_downloads/Apollo_Mapping_Imagery_Price_List.pdf)
- Tri-stereo gives clearly better urban DSMs than a single pair. Athens Pléiades-1B tri-stereo: RMSEz 1.17 m against 1.48-1.64 m for single pairs. — [Panagiotakis et al. 2018, IJGI](https://www.mdpi.com/2220-9964/7/3/118)
- For DSM matching, a convergence angle of about 5-15° works best (MicMac DSM-OPT service; no tie points found above 20°). — [Terradue DSM-OPT docs](https://docs.terradue.com/geohazards-tep/tutorials/dsm-opt.html); [Krauß et al. 2018](https://www.tandfonline.com/doi/full/10.1080/22797254.2018.1551069)

### Inferences
- Cheapest realistic Pléiades route if a set exists: Apollo Pléiades 1 stereo, 25 km² x $25 = $625; tri-stereo 25 km² x $37.50 = $937.50; Pléiades Neo stereo $1,062.50; Pléiades Neo tri-stereo $1,375 (list prices, before tax, my arithmetic). All need a sales quote, so none is self-service checkout. Covering the whole 50 km² box with Pléiades Neo tri-stereo ($2,750) is over budget.
- Pléiades 1A/1B have been out of service since 2022-2023 (from memory, confidence 70). Any Pléiades 1 stereo set of Rome is therefore 2012-2022 vintage.

### Gaps
- No stereo or tri-stereo scene IDs, dates or angles for Pléiades over Rome could be confirmed (catalogues need a login; EO-CAT unreachable from the sandbox).
- Manual check (a few clicks, free accounts):
  1. ESA EO-CAT, no login: https://eocat.esa.int → collections "Pleiades ESA archive", "PleiadesNeo" (ESA archive), "WorldView ESA archive" → draw the bbox → list results → look for 2-3 products on the same date, seconds apart, with different incidence/along-track angles.
  2. Airbus OneAtlas, free account: https://oneatlas.airbus.com → Search → draw the bbox → filter Pléiades + Pléiades Neo, cloud ≤ 10% → sort by date. Same-day groups with timestamps under about 1 min apart and incidence angles such as about 5°/15°/15° fore/aft are a stereo or tri-stereo set.
  3. Apollo Image Hunter, free login: https://imagehunter.apollomapping.com → draw the AOI → tick Pléiades, Pléiades Neo, WorldView, GeoEye, KOMPSAT → read the off-nadir/date columns. Or email sales@apollomapping.com with the bbox and ask for "archive in-track stereo/tri-stereo, Primary/Basic with RPC". Apollo staff do this search themselves.
  4. UP42 console catalogue: draw the AOI, then contact support for "stereo upon request".

## Q2. Vantor/Maxar WorldView, GeoEye-1, Legion and other sensors (KOMPSAT, SuperView, BJ3, Jilin, SkySat, BlackSky, Satellogic)

### Takeaway
Partly VERIFIED from literature: a GeoEye-1 in-track stereo pair over Rome exists, one of the first GeoEye-1 stereo pairs (about 2009). It is very likely still in the Vantor archive (confidence 70). There was no public way to list newer WorldView or Legion stereo over Rome. On reseller platforms, Vantor stereo is mostly sold as tasking or as non-integrated "Stereo System-Ready" on request.

### Cited Findings
- Sapienza (Capaldo, Crespi, Fratarcangeli, Nascetti, Pieralice) used "one of the first available GeoEye-1 stereo pairs, which was acquired over Rome". In dense urban areas their GeoEye-1 DSM reached only 8-10 m accuracy with their matcher. — [IRIS Sapienza 11573/438826](https://iris.uniroma1.it/handle/11573/438826); [IRIS 11573/410747](http://hdl.handle.net/11573/410747)
- WorldView-1 along-track stereo exists over the Colli Albani, south-east of Rome (outside the box). — [Bertacchini et al., UNIMORE](https://iris.unimo.it/handle/11380/1111895)
- Cartosat-1 (2.5 m) stereo of Rome, 8 Jun 2005, 53 s apart, B/H about 0.6 (ISPRS C-SAP test site TS-6/TS-8). Too coarse for building models. — [Crespi et al. 2006](http://hdl.handle.net/11573/361227)
- UP42 Vantor: "WorldView-3 Stereo System-Ready", "WorldView Legion Stereo System-Ready" and "GeoEye-1 Stereo System-Ready" are listed as "non-integrated data product", meaning ordered on request. Mono System-Ready (Primary) costs 2,200 credits/km² (WV-3/Legion) or 1,350 credits/km² (GeoEye-1). — [UP42 Vantor](https://docs.up42.com/data/vantor)
- SkyWatch (June 2026): Vantor 30 cm and 50 cm stereo have tasking prices only ($65 and $50/km², 50 km² minimum). Archive stereo price is "—", not published. — [SkyWatch Vantor](https://skywatch.com/geospatial-data-providers/vantor/)
- Apollo archive stereo list prices, 25 km² minimum unless noted: WorldView-3/Legion 30 cm $45/km² (Pan $35); GeoEye-1/WV-2/3 50 cm $30/km² (Pan $20); WorldView-1 50 cm Pan $20; KOMPSAT-3A $16 (25 km²); KOMPSAT-3 $16 (100 km²); BJ3N stereo $30 / tri-stereo $38; BJ3A stereo $24 / tri $30; SuperView Neo-1 $40 (100 km²); SuperView-2 $36 (100 km²); SuperView 1/2 50 cm $28 (100 km²); Jilin-1 $18 (100 km²); EROS-B stereo $20. — [Apollo price list PDF](https://apollomapping.com/image_downloads/Apollo_Mapping_Imagery_Price_List.pdf)
- UP42 acquisition modes: Beijing-3N mono/stereo/tri-stereo; BlackSky mono/stereo; KOMPSAT-3 mono/stereo; Satellogic mono only; Planet (SkySat) mono/stereo/tri-stereo. — [UP42 collection finder](https://docs.up42.com/data/collection-finder)
- Urban Atlas Building Height 2012 was made from WorldView-1/2/3, GeoEye-1, QuickBird and Ikonos imagery, using mostly "false stereo" pairs from different dates. That suggests true in-track stereo was not systematically available over EU capitals at the time. — [CLMS UA Building Height 2012](https://land.copernicus.eu/en/products/urban-atlas/building-height-2012); [UA BH PUM](https://library.land.copernicus.eu/products/Urban_Atlas_Building_Height_2012_PUM_v1.html)

### Inferences
- Cheapest list-price stereo that fits the budget, if a Rome set exists: GeoEye-1/WV 50 cm Pan stereo at 25 km² = $500, 4-band $750; WV-3 30 cm Pan stereo $875; KOMPSAT-3A stereo $400; BJ3N tri-stereo $950. Existence over Rome is UNKNOWN for all of them except GeoEye-1 (old pair).
- WorldView single-pair urban completeness is only 50-90% (Bologna WV-3 study). Vendor stereo pairs often have 32-47° convergence, which is poor for dense old towns. — [Mandanici et al. 2019](https://www.mdpi.com/2072-4292/11/7/878)

### Gaps
- No WorldView, Legion, KOMPSAT, SuperView, BJ3 or Jilin stereo scene IDs over Rome were seen. Vantor's discovery API needs credentials (api.maxar.com returned 403).
- Exact date, angles and B/H of the GeoEye-1 Rome pair were not found in the abstracts.

## Q3. Buying route, minimum order, delivery time, payment

### Takeaway
No vendor checked offers self-service, card-payable checkout of archive stereo with RPCs. Every route (UP42 "upon request", Apollo, SkyWatch, SkyFi) needs a human quote. A weekend order is unlikely to deliver before Monday (confidence 75).

### Cited Findings
- UP42: integrated catalogue scenes come "within a few days", and some scenes within 10 minutes. Stereo and Primary are non-integrated, upon request, with a 25 km² minimum. Credits are bought before checkout. — [UP42 Pléiades Neo](https://docs.up42.com/data/pleiades-neo); [UP42 catalog process](https://docs.up42.com/data/catalog-process); [UP42 min charges](https://docs.up42.com/data/catalog-min-charges)
- UP42 headline prices: "Archive from €6.80/km²"; elevation data archive from €2.00/km². — [UP42 pricing](https://up42.com/pricing)
- Apollo: archive is ordered through sales; academic discounts exist (see Q1). — [Apollo buy imagery](https://apollomapping.com/buy-imagery)
- SkyFi: archive stereo is not offered (given in brief); its API needs a key (verified 401).

### Inferences
- Credit conversion: UP42 1 credit = €0.01 (consistent with its €/km² headline prices; confidence 80).

### Gaps
- Exact turnaround for an on-request stereo order and whether any vendor processes it at a weekend: not documented.

## Q4. Licence: can a derived DSM / building heights / LoD2 model be published openly?

### Takeaway
NO for both Airbus and Vantor standard licences. Both explicitly exclude DEMs/DSMs (and, for Vantor, 3D/building models) from the freely distributable "derivative" class. A DSM built from bought stereo can be used internally but not put in a public repo without written permission (confidence 85).

### Cited Findings
- Airbus licence to use satellite data products (OneAtlas): "DERIVATIVE WORK ... does not contain any imagery data ... irreversible and uncoupled ... any Digital Elevation Model or Digital Terrain Model (in any form whatsoever) derived from a PRODUCT shall never be considered as DERIVATIVE WORKS". VAPs are for "internal purpose only"; only derivative works may be "freely used and distributed". — [Airbus standard licence PDF](https://www.intelligence-airbusds.com/files/pmedia/public/r51461_9_standard-licence-livinglibrary-210319.pdf); current licence index: [Airbus legal informations](https://space-solutions.airbus.com/oneatlas-my-services/legal-informations/)
- Vantor/Maxar EULA §2.3(b): Data Derivatives "specifically exclude ... orthorectified imagery ... DEM, DSM, DTM, TIN and Point Cloud elevation models (including, without limitation, 3D and building models...)". §5(a)/(c): no publishing and no publicly accessible storage. §3.1 Education licence: prior written consent is needed before publishing any product or derivative. — [Maxar group licence EULA (2022)](https://sg.geodatenzentrum.de/web_public/gdz/lizenz/sat4bund_eula/eusi_maxar/form_ww0024f_grouplicense_aktuell_2022.pdf); [Vantor legal](https://vantor.com/legal/)
- For Vantor Elevation Products (such as Vivid Terrain), a Data Derivative must "not contain any elevation, depth or height information". — same EULA

### Inferences
- What can be published: building footprints or a classification with no heights may count as Airbus "derivative work" (confidence 50; heights would not). LoD2 models with heights cannot.
- The Airbus PDF quoted is the 2019 Living Library version. I did not open the current "Standard End-User Licence Agreement" on the Airbus legal page, so the clause wording may differ (confidence 75 that the DEM exclusion remains).

### Gaps
- Whether ESA TPM-supplied data carries different terms. TPM is civilian, research, non-commercial use only, and the redistribution terms were not checked.

## Q5. Free or cheaper alternatives for a true DSM of Rome

### Takeaway
The biggest finding: an OPEN 1 m LiDAR DSM (DSM First/Last + DTM, CC BY 4.0) from the MASE Piano Straordinario di Telerilevamento already covers the Tiber corridor through the historic centre. VERIFIED by rendering the WMS: about 33% of the box (about 16 km²), including Campo Marzio/Pantheon, Trastevere, the Ghetto, Aventine and Testaccio. It does NOT cover the eastern part (Colosseum, Termini, Esquilino). It is old: flown 2008-2011.

### Cited Findings
- VERIFIED: a WMS GetMap of layer `EL.LIDAR.LAZIO.1x1.DSM_FIRST` over bbox 12.44,41.87,12.53,41.93 gave a 1 m hillshaded DSM. Coverage was 33% of pixels: a strip roughly lon 12.453-12.487 along the Tiber, with blocks reaching to about lat 41.93. My pixel check: Pantheon (12.477, 41.899) is inside, Colosseum (12.492, 41.890) is outside. — [MASE LiDAR Lazio WMS](http://wms.pcn.minambiente.it/ogc?map=/ms_ogc/WMS_v1.3/servizi-LiDAR/LIDAR_LAZIO.map&service=wms&request=getCapabilities&version=1.3.0)
- Lazio PST LiDAR DSM First metadata: 1 m, acquired 28 Feb 2008 to 5 Feb 2011 by BLOM CGR, river corridors of 1st/2nd order, CC BY 4.0. — [Geoportale metadata, DSM FIRST Lazio](http://www.pcn.minambiente.it/geoportal/catalog/search/resource/details.page?uuid=m_amte%3A299FN3%3Ad53d84c9-75c5-44fb-9d7e-88f4b22db95f)
- Download: free through the "Download Banca Dati PST" app (draw area, add to cart, ZIP of GeoTIFFs; up to 6 GB per request), CC BY 4.0. — [Geoportale MASE PST distribution](https://gn.mase.gov.it/portale/distribuzione-dati-pst); [app](https://sim.mase.gov.it/portalediaccesso/mappe/#/viewer/new); [tutorial](https://www.gisinfrastrutture.it/wp/wp-content/uploads/2026/02/Tutorial-Download-DTM-ad-alta-risoluzione-da-banca-dati-PST.pdf)
- Since 10 Nov 2026 the PST portal shows "a copertura territoriale ulteriormente ampliata" (further extended coverage) of 1 m DTM/DSM First/DSM Last. — [GEOmedia, 12 Nov 2026](https://mail.rivistageomedia.it/geodata/portale-pst-mase-aggiornamento-lidar-interferometria-2026)
- New national LiDAR (PNRR SIM, MASE/e-GEOS with CGR, more than 10 pts/m², whole Italy, 302,073 km²) began July 2025 and is to produce a new national DTM and DSM. Public release over Rome: not confirmed. — [MASE campaign launch](https://www.mase.gov.it/portale/-/pnrr-mase-parte-la-campagna-di-telerilevamento-aerospaziale-dati-per-pianificazione-sicurezza-idrogeologica-e-monitoraggio-ambientale); [GEOmedia Jul 2026](https://www.rivistageomedia.it/survey-and-positioning/nasce-il-nuovo-modello-digitale-del-territorio-italiano); [MASE SIM launch Feb 2026](https://www.mase.gov.it/portale/-/il-mase-lancia-sim-infrastruttura-per-la-sicurezza-ambientale-)
- Copernicus Urban Atlas Building Height: 10 m raster, 2012 edition covers capital cores (Rome included); a 2021 edition exists ("not yet validated"). Free for any purpose. Also in CDSE as BYOC collection 62887e25-816e-4f4e-be0e-5e0f5a6640c9. — [UA BH 2012](https://land.copernicus.eu/en/products/urban-atlas/building-height-2012); [UA BH 2021](https://land.copernicus.eu/en/products/urban-atlas/building-height-2021); [CDSE docs](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/clms/land-cover-and-use-in-priority-areas/urban-atlas/building-height/clms_ua_building-height_europe_10m_3yearly_v1.html); [HDS hub](https://hds.hub.copernicus.eu/datasets/hh-dataset-clms-urban-atlas-building-height-2012)
- AUBAC/CITERA (Sapienza) ran new LiDAR, multibeam and mobile-LiDAR surveys of the Roman Tiber reach in 2025-2026. Open release: not stated. — [AUBAC news, May 2026](https://aubac.it/news/notizie/governare-la-complessita-digitalizzazione-e-strategie-integrate-la-gestione-del-tevere)
- Ready-made commercial DSMs:
  - Vantor Vivid Terrain (formerly Precision3D) 50 cm DSM on UP42: 2,500 credits/km² (about €25), minimum 10 km², self-service catalogue, 3 m LE90 absolute. — [UP42 Vivid Terrain](https://docs.sa.up42.com/data/vivid-terrain)
  - SkyWatch: Vivid Terrain 50 cm $29.50/km², 10 km² minimum. — [SkyWatch](https://skywatch.com/geospatial-data-providers/vantor/)
  - Geoserve indicative prices: Precision3D DSM 0.5 m €24/km²; AW3D Enhanced DSM 0.5 m €40/km²; Elevation1 DSM €55/km². — [Geoserve](https://geoserve.nl/elevation-models/)
  - AW3D Enhanced minimum is 25 km². — [AW3D](https://www.aw3d.jp/en/products/enhanced/)
  - Airbus Elevation series minimum is 100 km². — [Apollo Elevation1](https://apollomapping.com/digital-elevation-models/elevation1-elevation4-elevation8)
- ESA TPM free routes:
  - "Pleiades ESA archive" and "WorldView ESA archive": Fast Registration with Approval, about 2 working days, institutional email required, downloads from tpm-ds.eo.esa.int/oads. — [Pleiades ESA archive](http://www.earth.esa.int/eogateway/catalog/pleiades-esa-archive); [TPM Data Access Guide](https://earth.esa.int/eogateway/documents/20142/37627/Third-Party-Mission-Data-Access-Guide.pdf)
  - "Full archive and tasking" (Pléiades, Pléiades Neo, WorldView, GeoEye-1): Project Proposal, evaluation "normally within 9 weeks" (the guide says 4-6 weeks). Quotas: Pléiades archive stereo 1,220 km², tri-stereo 813 km²; WorldView stereo quota halved. Civilian, non-commercial research only. — [WorldView-1 full archive](https://earth.esa.int/eogateway/catalog/worldview-1-full-archive-and-tasking); [ESA quota FAQ](https://earth.esa.int/eogateway/faq/how-much-data-may-i-request-in-a-project-proposal)
- Copernicus CCM VHR (VERIFIED records in Q1) are restricted to Copernicus services; not an access route for a hackathon team (confidence 80).

### Inferences
- For an open-source repo, the PST LiDAR DSM (CC BY 4.0) is the only verified, publishable, true 1 m DSM over part of central Rome. It needs only an attribution.
- For full box coverage: a Vivid Terrain 50 cm DSM of the whole box costs about €1,250 (50 km² x €25), or about €250 for a 10 km² core, self-service. It cannot be published openly (Vantor Elevation Product terms). Its 3 m LE90 and smoothing make it weaker than LiDAR for LoD2 (confidence 70).
- The ESA "Pleiades ESA archive" fast-approval route could give free Primary products within days if ESA happens to hold a Rome stereo set. That is unverified, and it needs an institutional email.

### Gaps
- Whether the 10 Nov 2026 PST update or the new PNRR national LiDAR already covers the eastern centre (Colosseum, Esquilino, Termini): not checked. Re-render the WMS or open the PST app to check.
- Regione Lazio, Città Metropolitana and Roma Capitale open DSM / 3D building data: not checked in this pass.
- Any research dataset with Pléiades/WorldView in-track stereo over Rome beyond the old GeoEye-1 pair: none found.
