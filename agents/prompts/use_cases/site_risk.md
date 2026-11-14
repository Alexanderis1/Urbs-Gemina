# School or hospital risk check

The tools have already run for one address: where it is, the sensitive sites and constraints around it, the official flood hazard areas (PGRA), the Seveso plant damage zones, the road underpasses, the official landslide areas, known underground cavities, past civil-protection interventions (2013-2022) and the emergency plan areas within the ring, air quality in its municipio, and ambulance reach in the district around it with flooded roads closed.

Write a risk sheet for the officer, one short section each:

1. **The site**: address, municipio, urban zone.
2. **Flood**: whether the ring touches a PGRA hazard area and which class; underpasses nearby.
3. **Ground**: landslide areas and underground cavities within the ring (cavities are sinkhole context, not a forecast).
4. **Past events**: how many civil-protection interventions the log holds within the ring, by kind (counts_by sottotipol), and the years of the listed ones (anno).
5. **Industrial**: whether it lies in a Seveso damage zone, and which plant and zone.
6. **Air**: the current reading in its municipio, with stations and uncertainty.
7. **Emergency reach**: residents the ambulance reaches within the target time in the district around the site, before and after the roads flooded by the forecast rain are closed.
8. **Around it**: other sensitive sites and constraints within the ring, with distance, and the emergency plan areas (waiting, reception) by name and type.

A hazard layer that returns nothing inside the ring means "none found in the official layer", not "no risk". This is context for the officer, not a safety certificate. At most 280 words.

Do not introduce yourself or say you are an AI: the system adds that line. Start with the content.
- Section headings carry no numbers and no citations; put each figure and its citation on its own bullet.
