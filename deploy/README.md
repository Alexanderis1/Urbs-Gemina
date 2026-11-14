# Hosting the tool API

Recommended: **Modal** (stable public URL, pay per second, free monthly credit). Fallback: the Docker image on the workstation behind a tunnel.

## Modal

From the repository root:

1. `pip install modal && modal setup` (once; logs in through the browser).
2. Create the secret with the API keys. A key's role is `office` or `citizen`; requests without a known key are served at the citizen tier.
   `modal secret create urbs-gemina-api URBS_API_KEYS="<long-random-office-key>:office"`
   Add to the same secret: `ANTHROPIC_API_KEY` (orchestrator), `EXA_API_KEY` (legal and dataset search), and `VOICE_SECRET_OFFICE` / `VOICE_SECRET_CITIZEN` (same values as the ElevenLabs workspace secrets).
3. `modal run deploy/modal_app.py::fetch_layers` downloads the static context layers into the volume `urbs-gemina-layers`.
4. `modal deploy deploy/modal_app.py` prints the public URL, `https://<workspace>--urbs-gemina-tools-api.modal.run`.
5. Check: open `<url>/docs` (interactive API page) and `<url>/health`.

`min_containers=1` keeps one container warm so the demo never waits on a cold start; set it to 0 after the hackathon.

## Workstation + tunnel

See the comments at the top of `deploy/Dockerfile`. Without Docker: `pip install -e ".[api]"` then `uvicorn twin.api.app:app --port 8000`.

## Who calls it

- Lovable edge functions (WS8) and the orchestrator (WS7) hold the office key in their secrets and send `Authorization: Bearer <key>`.
- The voice webhook (WS9) is mounted at `POST <url>/voice/ask_twin`; it goes through the orchestrator, never straight to the tools.
- Chat goes to `POST <url>/ask` (orchestrator, shared interface 7); the tier comes from the API key.
- The browser never sees the office key.
