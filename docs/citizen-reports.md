# Citizen reports ("Segnalazioni")

Added 14 Nov 2026 at Alessandro's request. Residents report an event in progress (heavy traffic, flooding, fire or smoke, an emergency, other) with a photo; the operations room sees the reports merged into candidate live events, each with a confidence and its reasons.

## Resident side (public service, `/segnala`)

Guided steps: sign in, what is happening, device GPS, photo, short text, check and send.

- **"Entra con SPID" is simulated.** Real SPID needs the city to be accredited as a service provider by AgID, which cannot be done in a hackathon. The button is labelled as a demo and opens an anonymous Lovable Cloud account (one per browser). No name, e-mail or tax code is stored.
- **GPS is required** (Alessandro, 14 Nov). Without the device position the report cannot be sent, and the screen explains how to turn it on.
- **The photo must carry its own GPS and time**, within 250 m of the device and taken less than 120 minutes ago (`config/signals.yaml`, `location_check`). "Scatta ora" takes the photo inside the app, so position and time come from the device at the moment of the shot. A gallery photo is read for its EXIF GPS and time.
- **Privacy.** The browser keeps only the distance and the age, then re-encodes the photo: all EXIF metadata is dropped before upload. Photos go to a private bucket.

## Staff side (operations workspace, `/segnalazioni`)

Tool `signal_events` (office only), code in `twin/tools/signals.py`:

1. Reports of the same category merge when close in space and time (radius and window per category).
2. Confidence is a log-odds sum: a prior (events are rare), one factor per independent account (capped at 5), a bonus for photos, the photo-GPS check (a photo taken elsewhere or long ago adds nothing), the twin layers read around the event (rain for flooding, road speed and bus delay for traffic, temperature for fire), and, when an officer asks, the Claude photo check and the Exa news check. Road speed fuses the simulated traffic loops, so its agreement counts at reduced weight and is labelled.
3. Levels: likely (75% or more), probable (45% or more), to be checked.

Tool `verify_signal` (office only, `agents/signal_check.py`): one Claude call (photos + texts, model `signals` in `config/agents.yaml`) and one Exa news search **per event, on request**, never per report. Claude only returns verdicts; the number comes from the code. Photos are fetched only from Lovable Cloud storage.

Staff never see who reported: the database view gives an opaque key per account so that one person counts once.

## To make it live

1. Apply `web/supabase/migrations/20261114050000_citizen_reports.sql` in Lovable Cloud and turn on **anonymous sign-ins** (Authentication settings).
2. Redeploy the tool API on Modal so it has `signal_events` and `verify_signal`.
3. Redeploy the `tools` edge function (it now lets office users call the two tools).

Without Lovable Cloud the app shows a sample: made-up reports (`scripts/make_sample_signals.py`), events computed by the real tool, labelled SAMPLE.
