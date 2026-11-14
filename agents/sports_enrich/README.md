# Facility enrichment agent (Challenge 04)

Exa Agent runs, batches of facilities as input rows, return disciplines, hours, accessibility and
organisational contacts, each with source URL, quote and confidence. `twin/modules/sports/web_fields.py`
then applies fixed rules: low confidence or missing source is dropped, accessibility stays "not known"
unless the quote states it, personal e-mails and mobile numbers are dropped, web values never replace
official or manager-confirmed ones. Effort `medium` by default.

    python -m twin.modules.sports.pipeline build
    python agents/sports_enrich/run.py --municipio VII
    python -m twin.modules.sports.pipeline build   # now with enrichment
