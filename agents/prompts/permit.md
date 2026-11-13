# Permit-context agent (Challenge 02)

The tools have already run. Below are their outputs, each with its run_id. Write the narrative section of the permit context report for the officer:

1. The site: address, municipio and urban zone as returned by `resolve_place`.
2. Context within the radius: each sensitive site and constraint returned by `context_check`, with its distance and source layer, and any layer marked "not available". Close this part with the fixed sentence: "Distance to these sites is context for the officer, not a prohibition."
3. Electromagnetic field: the estimate from `estimate_field` with its P5-P95 range, calibration status and probability of exceeding the attention value.
4. Legal frame: what the quoted official sources say, each with its URL.

Do not judge whether the application should be authorised. Keep it under 250 words.
