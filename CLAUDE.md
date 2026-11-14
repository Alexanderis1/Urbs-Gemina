# Project context for coding agents

Urbs Gemina: open digital twin of Rome for the public administration, built at AgenticHack Rome (13-14 Nov 2026). Read `docs/design-proposal.md` first, then `docs/decisions.md`. The organisers' own assistant manual is at https://agentic.urbe.build/manual/CLAUDE.md.

## Hard rules

- Open-source code, open-format data, **no personal data**. Drop contact fields at ingest.
- Every record and layer is `real`, `estimated` or `simulated`. Simulated data carries `synthetic=True` up to the UI.
- **Only traffic loop sensors may be simulated** (decided 13 Nov 2026). Every other sensor or layer uses real existing sources, filled in with mathematical models and sensor fusion, and is labelled `real` or `estimated`, never `simulated`. Scenario variants (what-ifs) are not sensors and may contain hypothetical inputs.
- Numbers come from deterministic tools, never from the language model.
- Legal thresholds live in `config/thresholds.yaml` only.
- Cartoradio data is read at runtime and never committed (`redistribution: false`).
- No Avalanche / blockchain. Provenance is the hash manifest plus git.
- Whole city by default; heavy simulations take an operating area (municipio, urban zone or polygon).
- Plans are ordered steps with go/no-go gates. Do not write time or effort estimates.

## Working style

- Test first: add or change a test in `tests/` before the code.
- After a series of changes run `python -m pytest` and `python -m mypy` (strict). Both must pass.
- New data source: add it to `data/manifest.json`, implement `twin.providers.base.Provider`, register it in `twin/providers/registry.py`, select it in `config/providers.yaml`.
- Keep assumptions in config files with a `basis:` note, not in code.

## Layout

`twin/providers` data sources · `twin/tools` deterministic tools · `twin/beliefs` mean + variance layers · `twin/scenarios` what-if engines · `twin/modules` antenna and sports applications · `twin/api` tool API · `agents` prompts and agent code · `voice` ElevenLabs · `web` Lovable front end · `eval` test sets · `scripts` one-off jobs · `config` settings · `data` manifest and git-ignored downloads · `docs` design and research.

## Current state

Gate A is next: `python scripts/fetch_static_layers.py` downloads the static context layers. See section 15 of the design proposal for the full build order.
