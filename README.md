# Urbs Gemina

*Rome's open digital twin. Every number shows how sure it is.*

An open digital twin of the whole city of Rome for the public administration, built at AgenticHack Rome (13-14 November 2026). It combines a 3D city model, official context layers, live public feeds and simulated sensors behind one interface, so officers can ask questions, watch the city, and test "what if" scenarios. It also answers Challenge 02 (mobile-phone antennas) and, as an add-on, Challenge 04 (sports facilities).

## Data honesty

Every layer is labelled **real**, **estimated** or **simulated** (see `data/manifest.json`). Loop sensors, the antenna register and field measurements are simulated today because the real ones are not public; the administration can switch to its own access in `config/providers.yaml`. Estimates always carry a range. Nothing here is an official measurement.

## What works in this scaffold

- Provider contract and registry (`twin/providers`), with a simulated loop-station provider
- Roma Capitale GeoServer reader that drops personal fields (`twin/providers/open/roma_wfs.py`)
- Deterministic 300 m context check (`twin/tools/context_check.py`)
- Field arithmetic: free-space field, combination with a baseline, range, exceedance probability (`twin/tools/emf.py`)
- Belief cell with update and decay (`twin/beliefs/cell.py`)
- Script that downloads the static context layers and records hashes (`scripts/fetch_static_layers.py`)

Everything else is planned; each folder has a README saying what goes there.

## Run

```
python -m venv .venv
.venv\Scripts\activate            # Windows   (source .venv/bin/activate elsewhere)
pip install -e ".[dev]"
python -m pytest
python -m mypy
python scripts/fetch_static_layers.py
```

## Documents

- `docs/design-proposal.md`: architecture, options, build order with gates
- `docs/decisions.md`: 3D viewer and hosting choices
- `docs/data-inventory.md`: every data source, endpoint, licence and price
- `docs/guardrails.md`: rules the agents and the app follow
- `DATA_LICENSES.md`: licence of each data source

## Licence

Code: MIT. Data: see `DATA_LICENSES.md`.
