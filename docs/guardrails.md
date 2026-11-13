# Guardrails

Each guardrail, and where it is enforced. "Code" means a deterministic check that the model cannot talk its way past.

| # | Guardrail | Enforced by |
|---|---|---|
| 1 | **Decision support only.** The system never approves, rejects or scores an application. The official decides (Legge 132/2025 art. 14; AgID guidelines for AI in the public administration, 9 Nov 2026). | Code: the verifier blocks decision wording (`config/agents.yaml` → `verifier.banned_phrases`, English and Italian). Prompt: answer contract. |
| 2 | **AI disclosure.** Chat banner and first sentence of every voice session say it is an AI (AI Act art. 50). | Code: the orchestrator prepends the disclosure line (`disclosure` in `config/agents.yaml`) to the first answer of a conversation. UI banner: WS8. Voice first line: WS9. |
| 3 | **Numbers come from tools.** Every figure carries a tool run id or a source URL; otherwise "insufficient data". | Code: `agents/verifier.py`. Each sentence with a number must cite `[run:…]`, `[src:…]` or `[data:…]`, and the number must appear in what it cites (rounding allowed, no new arithmetic). One rewrite, then the answer is replaced by "insufficient data" and the list of what is missing. |
| 4 | **Thresholds from config.** `config/thresholds.yaml` only. | Code: the permit agent reads the context radius from `thresholds.yaml`; the verifier accepts a threshold only from a tool run or a cited official source. No threshold appears in prompts. |
| 5 | **Distance is context, not a ban.** | Code: banned wording in the verifier. Prompt: the permit agent writes a fixed sentence. Report builder: WS4. |
| 6 | **Uncertainty is always shown.** Range, method and calibration status. | Code: any cited run with `p50` requires P5 and P95 in the answer, the word "estimate" and "calibrated/uncalibrated". |
| 7 | **Real / estimated / simulated.** | Code: a cited run with `synthetic: true` requires the word "simulated" in the answer; `TwinAnswer.data_kinds` and `synthetic` carry the labels to the UI. |
| 8 | **Role tiers.** Citizen tier: aggregates. Office tier: technical fields. | Tool API and database (WS4/WS8). The agent passes the server-set tier as the `x-urbs-role` header and never sets it itself. |
| 9 | **Untrusted web content.** Quoted data with provenance; no state-changing tool in the same turn. | Code: Exa results are re-filtered to the allowed domains (no look-alike hosts), scanned for injection phrases (flagged, not trusted), and wrapped in `<untrusted_web_content source=… retrieved_at=…>` with any fake closing tag neutralised. Once web content enters a turn, the loop refuses every tool marked state-changing. The data steward scans and proposes in two separate steps; proposals wait for human approval. |
| 10 | **Heavy-run limits.** | Tool API refuses (`status: "refused"`); the agent reports the reason and proposes a smaller area. The scenario agent will not call `run_scenario` until kind, area and change are given. |
| 11 | **Privacy.** Personal contact fields dropped at ingest; logs keep addresses at street level only. | Ingest (WS1). The agents store no conversation text. |
| 12 | **Provenance.** SHA-256 of every dataset snapshot, simulation run and report. | Envelope `run_id` (tool + inputs + snapshot hashes). Exa runs hash the kept results and the domain list. |
| 13 | **Restricted data.** Cartoradio is read at runtime only and never committed. | Providers (WS3). |
| 14 | **Missing data is said, never filled.** | Code: results with `status` `not_available` or `refused` cannot vouch for any figure; their `reason` is listed in `TwinAnswer.missing`. |

## Tested by

`tests/test_agents_*.py` and the eval sets in `eval/sets/` (`python -m eval.run_eval`).
