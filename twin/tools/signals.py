"""Citizen reports ("segnalazioni") merged into candidate live events, with a confidence.

Deterministic: the same reports, twin readings and checks always give the same events and numbers.

1. Reports of the same category that are close in space and time merge into one event
   (greedy, in time order; radius and window per category from ``config/signals.yaml``).
2. Confidence is a log-odds sum: a prior, one likelihood ratio per independent reporter
   (an account counts once, capped), a bonus for photos, the agreement of twin layers read
   around the event, and the optional photo/news check done once per event by Claude + Exa.
3. Reporter keys never leave this module: events carry counts only.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from twin.tools.settings import default_paths, load_yaml

#: Reads one twin layer inside a GeoJSON polygon and returns a tool envelope (``query_layer``).
LayerReader = Callable[[str, dict[str, Any]], Mapping[str, Any]]

M_PER_DEG_LAT = 111_195.0
ROME_BBOX = (12.0, 41.4, 13.1, 42.4)
VERDICTS = ("supports", "contradicts", "neutral", "not_available")


def load_signal_config(path: Path | None = None) -> dict[str, Any]:
    return load_yaml(path or default_paths().config / "signals.yaml")


def categories(cfg: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {k: dict(v) for k, v in cfg["categories"].items() if isinstance(v, Mapping)}


@dataclass(frozen=True)
class Report:
    id: str
    category: str
    lon: float
    lat: float
    time: datetime
    reporter: str
    has_photo: bool = False
    text: str = ""
    photo_ref: str | None = None
    location: str = "missing"   # photo GPS/time vs device GPS: match | mismatch | missing
    subtype: str | None = None


@dataclass
class Cluster:
    category: str
    reports: list[Report] = field(default_factory=list)

    @property
    def report_ids(self) -> list[str]:
        return [r.id for r in self.reports]

    @property
    def n_reports(self) -> int:
        return len(self.reports)

    @property
    def n_reporters(self) -> int:
        return len({r.reporter for r in self.reports})

    @property
    def reporters_with_photo(self) -> int:
        return len({r.reporter for r in self.reports if r.has_photo and r.location != "mismatch"})

    def reporter_locations(self) -> list[str]:
        """Best photo-location check per independent reporter (match > missing > mismatch)."""
        rank = {"match": 0, "missing": 1, "mismatch": 2}
        best: dict[str, str] = {}
        for r in self.reports:
            if r.reporter not in best or rank[r.location] < rank[best[r.reporter]]:
                best[r.reporter] = r.location
        return sorted(best.values(), key=lambda v: rank[v])

    @property
    def centre(self) -> tuple[float, float]:
        n = len(self.reports)
        return sum(r.lon for r in self.reports) / n, sum(r.lat for r in self.reports) / n

    @property
    def first_seen(self) -> datetime:
        return min(r.time for r in self.reports)

    @property
    def last_seen(self) -> datetime:
        return max(r.time for r in self.reports)

    @property
    def radius_m(self) -> float:
        lon, lat = self.centre
        return max(distance_m(lon, lat, r.lon, r.lat) for r in self.reports)

    @property
    def id(self) -> str:
        # The earliest report names the event, so the id stays the same as reports are added.
        first = min(self.reports, key=lambda r: (r.time, r.id))
        return "sig-" + hashlib.sha256(first.id.encode("utf-8")).hexdigest()[:10]


def distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000.0 * math.asin(math.sqrt(a))


def parse_time(value: Any) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def location_check(distance_m: float | None, age_min: float | None, cfg: Mapping[str, Any]) -> str:
    """Does the photo's own GPS and time agree with the device GPS when the report was sent?"""
    if distance_m is None or age_min is None:
        return "missing"
    lc = cfg.get("location_check") or {}
    ok = float(distance_m) <= float(lc.get("max_distance_m", 250)) and -5 <= float(age_min) <= float(lc.get("max_age_min", 120))
    return "match" if ok else "mismatch"


def _subtype(spec: Mapping[str, Any], value: Any) -> str | None:
    known = spec.get("subtypes") or {}
    return str(value) if value is not None and str(value) in known else None


def _opt_float(value: Any) -> float | None:
    return None if value is None else float(value)


def parse_reports(raw: Iterable[Mapping[str, Any]], cfg: Mapping[str, Any],
                  warnings: list[str] | None = None) -> list[Report]:
    """Valid reports only; each dropped one adds a warning (never the reporter key)."""
    cats = categories(cfg)
    max_chars = int(cfg.get("max_text_chars", 280))
    out: list[Report] = []
    for item in raw:
        rid = str(item.get("id", "?"))
        try:
            category = str(item["category"])
            if category not in cats:
                raise ValueError(f"unknown category '{category}'")
            lon, lat = float(item["lon"]), float(item["lat"])
            if not (ROME_BBOX[0] <= lon <= ROME_BBOX[2] and ROME_BBOX[1] <= lat <= ROME_BBOX[3]):
                raise ValueError("place outside the Rome area")
            out.append(Report(id=rid, category=category, lon=lon, lat=lat, time=parse_time(item["time"]),
                              reporter=str(item.get("reporter") or rid), has_photo=bool(item.get("has_photo")),
                              text=str(item.get("text") or "")[:max_chars],
                              photo_ref=str(item["photo_ref"]) if item.get("photo_ref") else None,
                              location=location_check(_opt_float(item.get("photo_gps_distance_m")),
                                                      _opt_float(item.get("photo_age_min")), cfg),
                              subtype=_subtype(cats[category], item.get("subtype"))))
        except (KeyError, TypeError, ValueError) as error:
            if warnings is not None:
                warnings.append(f"report {rid} dropped: {error}")
    return out


def cluster_reports(reports: Sequence[Report], cfg: Mapping[str, Any]) -> list[Cluster]:
    """Greedy merge in time order: a report joins the nearest open event of its category."""
    cats = categories(cfg)
    clusters: list[Cluster] = []
    for report in sorted(reports, key=lambda r: (r.time, r.id)):
        spec = cats[report.category]
        radius, window = float(spec["radius_m"]), timedelta(minutes=float(spec["window_min"]))
        best: tuple[float, Cluster] | None = None
        for cluster in clusters:
            if cluster.category != report.category or report.time - cluster.last_seen > window:
                continue
            d = distance_m(*cluster.centre, report.lon, report.lat)
            if d <= radius and (best is None or d < best[0]):
                best = (d, cluster)
        if best is None:
            clusters.append(Cluster(report.category, [report]))
        else:
            best[1].reports.append(report)
    return clusters


def _square(lon: float, lat: float, half_m: float) -> dict[str, Any]:
    d_lat = half_m / M_PER_DEG_LAT
    d_lon = half_m / (M_PER_DEG_LAT * math.cos(math.radians(lat)))
    ring = [[lon - d_lon, lat - d_lat], [lon + d_lon, lat - d_lat], [lon + d_lon, lat + d_lat],
            [lon - d_lon, lat + d_lat], [lon - d_lon, lat - d_lat]]
    return {"type": "Polygon", "coordinates": [[[round(x, 6), round(y, 6)] for x, y in ring]]}


def _holds(value: float, cond: Mapping[str, Any] | None) -> bool:
    if not cond:
        return False
    op, ref = str(cond["op"]), float(cond["value"])
    return {"<=": value <= ref, ">=": value >= ref, "<": value < ref, ">": value > ref}[op]


def _cell_values(envelope: Mapping[str, Any]) -> list[float]:
    result = envelope.get("result") or {}
    cells = result.get("cells") if isinstance(result, Mapping) else None
    values: list[float] = []
    columns = list(result.get("cell_columns") or []) if isinstance(result, Mapping) else []
    for cell in cells or []:
        if isinstance(cell, Mapping) and cell.get("mean") is not None:
            values.append(float(cell["mean"]))
        elif isinstance(cell, Sequence) and "mean" in columns:
            values.append(float(cell[columns.index("mean")]))
    return values


def twin_evidence(cluster: Cluster, cfg: Mapping[str, Any], read_layer: LayerReader) -> list[dict[str, Any]]:
    """Read each configured twin layer around the event and say whether it supports the report."""
    checks_cfg = cfg.get("twin_checks") or {}
    checks = list(checks_cfg.get(cluster.category) or [])
    if not checks:
        return []
    lon, lat = cluster.centre
    area = _square(lon, lat, max(cluster.radius_m, float(checks_cfg.get("area_half_m", 300))))
    power = float(cfg["confidence"].get("simulated_evidence_power", 0.5))
    out: list[dict[str, Any]] = []
    for check in checks:
        layer = str(check["layer"])
        row: dict[str, Any] = {"layer": layer, "unit": check.get("unit"), "basis": check.get("basis"),
                               "verdict": "not_available", "lr": 1.0, "value": None, "simulated_input": False}
        try:
            env = read_layer(layer, area)
        except Exception as error:  # noqa: BLE001 - a feed being down must never hide the citizen reports
            out.append({**row, "reason": f"{type(error).__name__}: {error}"})
            continue
        values = _cell_values(env) if env.get("status") == "ok" else []
        if not values:
            out.append({**row, "reason": str(env.get("reason") or "no value around the place")})
            continue
        stat = str(check.get("stat", "mean"))
        value = max(values) if stat == "max" else min(values) if stat == "min" else sum(values) / len(values)
        simulated = bool(env.get("synthetic"))
        if _holds(value, check.get("supports")):
            verdict, lr = "supports", float(check.get("supports_lr", 1.0))
        elif _holds(value, check.get("contradicts")):
            verdict, lr = "contradicts", float(check.get("contradicts_lr", 1.0))
        else:
            verdict, lr = "neutral", 1.0
        if simulated:
            lr = lr ** power
        out.append({**row, "verdict": verdict, "lr": round(lr, 4), "value": round(value, 2),
                    "simulated_input": simulated})
    return out


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def score_cluster(cluster: Cluster, cfg: Mapping[str, Any], twin: Sequence[Mapping[str, Any]] = (),
                  checks: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Confidence that the event is real, with every factor listed (log-odds, so they add up)."""
    c = cfg["confidence"]
    factors: list[dict[str, Any]] = [{"factor": "prior", "lr": None, "p": float(c["prior"])}]
    log_odds = _logit(float(c["prior"]))
    power = {k: float(v) for k, v in (c.get("location_power") or {"match": 1.0, "missing": 1.0, "mismatch": 1.0}).items()}
    counted_locs = cluster.reporter_locations()[: int(c["max_reporters_counted"])]
    weight = sum(power[loc] for loc in counted_locs)
    counted = len(counted_locs)
    photos = min(cluster.reporters_with_photo, counted)

    def add(name: str, lr: float, detail: str) -> None:
        nonlocal log_odds
        if lr <= 0:
            raise ValueError(f"likelihood ratio must be positive: {name}")
        log_odds += math.log(lr)
        factors.append({"factor": name, "lr": round(lr, 4), "detail": detail})

    mismatched = counted_locs.count("mismatch")
    add("reporters", float(c["reporter_lr"]) ** weight,
        f"{cluster.n_reporters} independent reporter(s), {counted} counted"
        + (f", {mismatched} with a photo taken elsewhere or long ago" if mismatched else ""))
    if photos:
        add("photos", float(c["photo_lr"]) ** photos, f"{photos} reporter(s) attached a photo")
    for row in twin:
        if row.get("verdict") in ("supports", "contradicts"):
            add(f"twin:{row['layer']}", float(row["lr"]), f"{row['layer']} {row['verdict']} the report")
    lrs = c.get("checks") or {}
    for key, name in (("photo", "photo_check"), ("news", "news_check")):
        verdict = (checks or {}).get(key)
        if verdict:
            if verdict not in lrs.get(key, {}):
                raise ValueError(f"unknown {key} verdict '{verdict}'")
            add(name, float(lrs[key][verdict]), f"{key}: {verdict}")
    p = 1 / (1 + math.exp(-log_odds))
    levels = c["levels"]
    level = "likely" if p >= float(levels["likely"]) else "probable" if p >= float(levels["probable"]) else "unconfirmed"
    return {"confidence": round(p, 3), "level": level, "factors": factors}


def signal_events(raw_reports: Iterable[Mapping[str, Any]], cfg: Mapping[str, Any],
                  read_layer: LayerReader | None = None, checks: Mapping[str, Mapping[str, str]] | None = None,
                  now: Any = None) -> dict[str, Any]:
    """Events for the staff map, most confident first. Reporter keys never appear in the output."""
    warnings: list[str] = []
    raw = list(raw_reports)
    limit = int(cfg.get("max_reports", 2000))
    if len(raw) > limit:
        warnings.append(f"only the {limit} most recent reports are used ({len(raw)} sent)")
        raw = sorted(raw, key=lambda r: str(r.get("time", "")))[-limit:]
    reports = parse_reports(raw, cfg, warnings)
    clusters = cluster_reports(reports, cfg)
    at = parse_time(now) if now is not None else datetime.now(timezone.utc).replace(microsecond=0)
    stale = timedelta(minutes=float(cfg.get("stale_after_min", 180)))
    cats = categories(cfg)
    events: list[dict[str, Any]] = []
    for cluster in clusters:
        scored = bool(cats[cluster.category].get("scored", True))
        twin = twin_evidence(cluster, cfg, read_layer) if read_layer is not None and scored else []
        score: dict[str, Any] = (score_cluster(cluster, cfg, twin, (checks or {}).get(cluster.id)) if scored
                                 else {"confidence": None, "level": "not_scored", "factors": []})
        subtypes: dict[str, int] = {}
        for r in cluster.reports:
            if r.subtype:
                subtypes[r.subtype] = subtypes.get(r.subtype, 0) + 1
        lon, lat = cluster.centre
        events.append({
            "id": cluster.id,
            "category": cluster.category,
            "category_label": cats[cluster.category].get("label", cluster.category),
            "scored": scored,
            "subtypes": subtypes,
            "lon": round(lon, 6), "lat": round(lat, 6),
            "radius_m": round(cluster.radius_m),
            "first_seen": cluster.first_seen.isoformat(), "last_seen": cluster.last_seen.isoformat(),
            "stale": at - cluster.last_seen > stale,
            "n_reports": cluster.n_reports, "n_reporters": cluster.n_reporters,
            "n_photos": sum(1 for r in cluster.reports if r.has_photo),
            "n_location_match": sum(1 for r in cluster.reports if r.location == "match"),
            "n_location_mismatch": sum(1 for r in cluster.reports if r.location == "mismatch"),
            "report_ids": cluster.report_ids,
            "photo_refs": [r.photo_ref for r in cluster.reports if r.photo_ref],
            "texts": [r.text for r in cluster.reports if r.text],
            "twin": twin,
            "checks": dict((checks or {}).get(cluster.id) or {}),
            **score,
        })
    events.sort(key=lambda e: (not e["scored"], -(e["confidence"] or 0.0), -e["n_reports"], e["id"]))
    return {"events": events, "n_reports": len(reports), "as_of": at.isoformat(), "warnings": warnings}
