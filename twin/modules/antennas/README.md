# Antenna module (Challenge 02)

Permit-context flow: address -> 300 m context check on official layers -> estimated field with range (cartoradio baseline + twin model for the new source) -> cited report. Antenna positions are estimates; authorisation status is simulated. See `docs/design-proposal.md` sections 9a, 10 and 11.

`report.build_permit_report(runtime, place=... | point=..., proposed_antennas=[...])` chains `resolve_place`, `context_check` and `estimate_field`, and returns a Markdown report in which every number carries the run id of the tool that produced it, plus the SHA-256 of the report. Fixed wording: "decision support only" and "context, not a ban". Served as the `permit_report` tool and `POST /reports/permit.md`.
