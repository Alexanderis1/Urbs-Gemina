"""Writes web/src/api/sampleSignals.json: the staff 'Segnalazioni' layer in the demo build without Lovable Cloud.

The reports below are made up for the demo (shown as SAMPLE in the UI); the events and confidences are
computed by the real tool code (twin.tools.signals), without twin layers or Claude/Exa checks.
Run: python scripts/make_sample_signals.py
"""
from __future__ import annotations

import json
from pathlib import Path

from twin.tools.signals import load_signal_config, signal_events

NOW = "2026-11-14T08:30:00Z"


def r(i: int, cat: str, lon: float, lat: float, minute: int, text: str, who: str | None = None,
      dist: float = 40.0, age: float = 3.0) -> dict[str, object]:
    return {"id": f"sample-{i}", "category": cat, "lon": lon, "lat": lat, "time": f"2026-11-14T08:{minute:02d}:00Z",
            "reporter": who or f"sample-reporter-{i}", "has_photo": True, "text": text,
            "photo_gps_distance_m": dist, "photo_age_min": age}


REPORTS = [
    r(1, "flood", 12.5205, 41.9230, 2, "Sottopasso di via Salaria pieno d'acqua, auto ferme"),
    r(2, "flood", 12.5212, 41.9226, 6, "Acqua alta nel sottopasso, non si passa"),
    r(3, "flood", 12.5199, 41.9235, 11, "Allagamento sottopasso, tombini che rigurgitano"),
    r(4, "congestion", 12.4920, 41.8902, 15, "Coda ferma su via Labicana verso il Colosseo"),
    r(5, "congestion", 12.4935, 41.8897, 19, "Traffico bloccato, incidente?"),
    r(6, "fire", 12.4433, 41.8601, 21, "Fumo nero dal parco, sembra sterpaglia"),
    r(7, "emergency", 12.4769, 41.9010, 24, "Calcinacci caduti dal cornicione", dist=4200.0, age=2900.0),
]

if __name__ == "__main__":
    out = signal_events(REPORTS, load_signal_config(), None, None, NOW)
    path = Path(__file__).resolve().parents[1] / "web" / "src" / "api" / "sampleSignals.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(out['events'])} events)")
