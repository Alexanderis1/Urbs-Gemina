"""Writes web/src/api/sampleSignals.json: the staff 'Segnalazioni' layer in the demo build without Lovable Cloud.

The reports below are made up for the demo (shown as SAMPLE in the UI); the events and confidences are
computed by the real tool code (twin.tools.signals), without twin layers or Claude/Exa checks.
Run: python scripts/make_sample_signals.py
"""
from __future__ import annotations

import json
from pathlib import Path

from twin.tools.maintenance import plan_maintenance
from twin.tools.signals import load_signal_config, signal_events

NOW = "2026-11-14T08:30:00Z"


def r(i: int, cat: str, lon: float, lat: float, minute: int, text: str, sub: str | None = None,
      dist: float = 40.0, age: float = 3.0, photo: bool = True) -> dict[str, object]:
    return {"id": f"sample-{i}", "category": cat, "subtype": sub, "lon": lon, "lat": lat,
            "time": f"2026-11-14T08:{minute:02d}:00Z", "reporter": f"sample-reporter-{i}", "has_photo": photo,
            "text": text, **({"photo_gps_distance_m": dist, "photo_age_min": age} if photo else {})}


REPORTS = [
    r(1, "flood", 12.5205, 41.9230, 2, "Sottopasso di via Salaria pieno d'acqua, auto ferme", "flood"),
    r(2, "flood", 12.5212, 41.9226, 6, "Acqua alta nel sottopasso, non si passa", "flood"),
    r(3, "flood", 12.5199, 41.9235, 11, "Tombini che rigurgitano all'ingresso del sottopasso", "sewer"),
    r(4, "traffic", 12.4920, 41.8902, 15, "Incidente tra due auto, coda ferma su via Labicana", "incident"),
    r(5, "traffic", 12.4935, 41.8897, 19, "Traffico bloccato verso il Colosseo", "congestion"),
    r(6, "pothole", 12.5291, 41.8752, 21, "Buca profonda sulla corsia di destra, pericolosa per gli scooter"),
    r(7, "pothole", 12.5292, 41.8751, 27, "Buca grande davanti alla fermata"),
    r(8, "pothole", 12.4581, 41.8803, 23, "Buca vicino al marciapiede"),
    r(9, "roadworks", 12.4702, 41.9065, 24, "Cantiere aperto stamattina, senza cartello"),
    r(10, "flood", 12.4433, 41.8601, 25, "Tombino otturato", "sewer", dist=4200.0, age=2900.0),
    r(11, "public_event", 12.4731, 41.8956, 28, "Concerto gratuito in piazza stasera alle 21", photo=False),
]

# A morning of road and sewer reports across the city: each place reported by two people (fixed coordinates).
POTHOLES = [(12.5102, 41.9012), (12.5355, 41.8869), (12.5478, 41.8781), (12.5590, 41.8705), (12.4498, 41.8712),
            (12.4612, 41.8650), (12.4305, 41.8902), (12.4885, 41.9301), (12.5011, 41.9405), (12.5243, 41.9118)]
SEWERS = [(12.5150, 41.8600), (12.4700, 41.9450), (12.4400, 41.9000), (12.5400, 41.9000)]
EXTRA = []
for k, (lon, lat) in enumerate(POTHOLES):
    EXTRA += [r(100 + 2 * k, "pothole", lon, lat, 30 + k, "Buca pericolosa sull'asfalto"),
              r(101 + 2 * k, "pothole", lon + 0.00005, lat, 40 + k, "Buca profonda, auto che sbandano")]
for k, (lon, lat) in enumerate(SEWERS):
    EXTRA += [r(200 + 2 * k, "flood", lon, lat, 31 + k, "Tombino otturato, acqua in strada", "sewer"),
              r(201 + 2 * k, "flood", lon, lat + 0.0001, 45 + k, "Fogna che rigurgita", "sewer")]
REPORTS += EXTRA

if __name__ == "__main__":
    cfg = load_signal_config()
    out = signal_events(REPORTS, cfg, None, None, NOW)
    web = Path(__file__).resolve().parents[1] / "web" / "src" / "api"
    (web / "sampleSignals.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    plan = plan_maintenance(out["events"], cfg, {"roads": 2, "sewers": 1})
    (web / "sampleMaintenance.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(out['events'])} sample events and a plan with {plan['total']['stops']} stops")
