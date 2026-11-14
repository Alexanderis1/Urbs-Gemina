# Sports scout agent (Challenge 04)

One Exa Agent run per municipio finds facilities missing from the official registers (mainly school
gyms assigned to associations). It **proposes** candidates with a source URL, quote and confidence. The
deterministic code in `twin/modules/sports/web_fields.py` decides what is kept, and everything kept is
labelled "from the web, unverified" until a manager confirms it.

- `prompt.md`: instructions (system prompt), `schema.json`: output schema
- `run.py municipio:7`: runs it, writes `data/raw/sports_web/scout_VII.json`
- `exa_agent.py`: small client for `POST https://api.exa.ai/agent/runs`, shared with `sports_enrich`
- Effort: `low` by default (decision in the WS10 thread).
