# Guardrails

1. **Decision support only.** The system never approves, rejects or scores an application. The official decides (Legge 132/2025 art. 14; AgID guidelines for AI in the public administration, 9 Nov 2026).
2. **AI disclosure.** Chat banner and first sentence of every voice session say it is an AI (AI Act art. 50).
3. **Numbers come from tools.** Distances, fields, counts and thresholds are produced by deterministic tools. Every figure in an answer carries a tool run id or a source URL. Otherwise the answer is "insufficient data".
4. **Thresholds from config.** `config/thresholds.yaml`, with citation and as-of date. Never in code or prompts.
5. **Distance is context, not a ban.** Fixed wording in every permit report.
6. **Uncertainty is always shown.** Range, method and calibration status.
7. **Real / estimated / simulated.** Every layer and record is labelled. Simulated data shows a SIMULATED badge.
8. **Role tiers.** Citizen tier: aggregated antenna data. Office tier: technical fields. Enforced in the API and the database, not in the prompt.
9. **Untrusted web content.** Search results enter as quoted data with provenance. No state-changing tool may run in the same turn.
10. **Heavy-run limits.** Micro traffic simulation and ray tracing refuse areas above `heavy_tools_max_area_km2`.
11. **Privacy.** Personal contact fields are dropped at ingest. No video. Logs keep addresses at street level only.
12. **Provenance.** SHA-256 of every dataset snapshot, simulation run and report in `data/manifest.json` and git.
13. **Restricted data.** Cartoradio is read at runtime only and never committed (`redistribution: false`).
