"""Cited permit-context report for Challenge 02.

Chains the deterministic tools (resolve_place -> context_check ->
estimate_field), keeps every tool envelope, and writes a Markdown report in
which every number carries the run id of the tool that produced it. The report
gets a SHA-256 so a "Verify" view can re-hash it. No language model is involved.
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping

from twin.tools.envelope import ToolError, utc_now
from twin.tools.estimate_field import estimate_field
from twin.tools.permit_context import run_context_check
from twin.tools.resolve_place import resolve_place
from twin.tools.runtime import ToolRuntime

TOOL = "permit_report"
DISCLAIMER = ("Decision support only. This report does not approve, reject or score an application: "
              "the responsible official decides.")


def _ref(envelope: Mapping[str, Any]) -> str:
    return f"[run {str(envelope['run_id'])[:12]}]"


def _fmt(value: Any, unit: str = "") -> str:
    if value is None:
        return "n/a"
    return f"{value:g} {unit}".strip() if isinstance(value, (int, float)) else str(value)


def build_permit_report(runtime: ToolRuntime, place: str | None = None, point: Mapping[str, float] | None = None,
                        proposed_antennas: list[dict[str, Any]] | None = None, radius_m: float | None = None,
                        role: str = "office") -> dict[str, Any]:
    if (place is None) == (point is None):
        raise ToolError("give exactly one of 'place' or 'point'")
    runs: list[dict[str, Any]] = []
    if place is not None:
        located = resolve_place(runtime, place)
        runs.append(located)
        if not located["result"].get("found"):
            raise ToolError(f"place not found: {place}")
        lon, lat = float(located["result"]["lon"]), float(located["result"]["lat"])
    else:
        assert point is not None
        lon, lat = float(point["lon"]), float(point["lat"])
        located = resolve_place(runtime, f"{lat}, {lon}")
        runs.append(located)

    context = run_context_check(runtime, lon, lat, radius_m, include_properties=role == "office")
    runs.append(context)
    variant = {"add_antennas": proposed_antennas} if proposed_antennas else None
    field = estimate_field(runtime, point={"lon": lon, "lat": lat}, variant=variant)
    runs.append(field)

    markdown = _markdown(runtime, place or f"{lat:.5f}, {lon:.5f}", located, context, field)
    digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    synthetic = any(run["synthetic"] for run in runs)
    kinds: dict[str, str] = {}
    for run in runs:
        kinds.update(run["data_kinds"])
    result = {
        "report_sha256": digest,
        "generated_at": utc_now(),
        "title": f"Permit context report: {place or f'{lat:.5f}, {lon:.5f}'}",
        "markdown": markdown,
        "tool_runs": runs,
    }
    inputs = {"place": place, "point": dict(point) if point else None, "proposed_antennas": proposed_antennas,
              "radius_m": radius_m, "role": role}
    warnings = [w for run in runs for w in run["warnings"]]
    return runtime.envelope(TOOL, inputs, result, kinds, warnings=warnings, synthetic=synthetic,
                         extra_hashes={run["tool"] + ":" + run["run_id"][:12]: run["run_id"] for run in runs})


def _markdown(runtime: ToolRuntime, title: str, located: dict[str, Any], context: dict[str, Any],
              field: dict[str, Any]) -> str:
    loc, ctx, est = located["result"], context["result"], field["result"]
    thresholds = runtime.settings.thresholds
    lines = [f"# Permit context report: {title}", "", f"> {DISCLAIMER}", "",
             "> Every number below comes from a deterministic tool; the run id after it lets you re-run and verify it.",
             ""]
    if any(run["synthetic"] for run in (located, context, field)):
        lines += ["> **SIMULATED** data is used in part of this report.", ""]

    lines += ["## 1. Location", ""]
    mun, zone = loc.get("municipio", {}), loc.get("urban_zone", {})
    lines += [f"- Coordinates: {loc['lat']}, {loc['lon']} ({loc['method']}, precision {loc['precision']}) "
              f"{_ref(located)}",
              f"- Municipio: {mun.get('name') or mun.get('id') or mun.get('status', 'n/a')}",
              f"- Urban zone: {zone.get('name') or zone.get('id') or zone.get('status', 'n/a')}", ""]

    lines += [f"## 2. Within {ctx['radius_m']:g} m", "", f"*{ctx['meaning']}*", ""]
    for group in ctx["groups"].values():
        lines += [f"### {group['label']}", "", "| Layer | Count | Nearest | Distance |", "|---|---|---|---|"]
        for layer in group["layers"]:
            if layer["status"] != "ok":
                lines.append(f"| {layer['label']} | not available | | |")
                continue
            nearest = layer["hits"][0] if layer["hits"] else None
            name = (nearest["name"] or "(unnamed)") if nearest else ""
            distance = "" if nearest is None else "inside" if nearest["distance_m"] == 0 else _fmt(
                nearest["distance_m"], "m")
            lines.append(f"| {layer['label']} | {layer['count']} | {name} | {distance} |")
        lines.append("")
    lines += [f"Source run: {_ref(context)}", ""]

    lines += ["## 3. Estimated electric field", ""]
    if est is None:
        lines += ["Insufficient data: no baseline and no proposed antenna. " + _ref(field), ""]
    else:
        base = est.get("baseline")
        if base:
            lines.append(f"- Official baseline (Cartoradio): {_fmt(base['value_v_per_m'], 'V/m')}"
                         f"{' (cap: read as 15 V/m or more)' if base['capped'] else ''}. {base['credit']}")
        else:
            lines.append("- Official baseline (Cartoradio): not available; the total below covers only the "
                         "proposed antennas.")
        for antenna in est.get("new_sources", []):
            lines.append(f"- Proposed antenna at {antenna['distance_m']:g} m, EIRP {antenna['eirp_w']:g} W "
                         f"({antenna['eirp_basis']}): {_fmt(antenna['field_p50_v_per_m'], 'V/m')}")
        measured = est.get("nearest_measurement")
        if measured:
            lines.append(f"- Nearest real measurement ({measured['source']}): {_fmt(measured['value_v_per_m'], 'V/m')} "
                         f"at {measured['distance_m']:g} m. Reference only, not part of the estimate.")
        lines += [f"- Total field: P5 {_fmt(est['p5'])} / P50 {_fmt(est['p50'])} / P95 {_fmt(est['p95'])} V/m "
                  f"{_ref(field)}"]
        for name, ex in est["exceedance"].items():
            label = name.replace("_", " ")
            lines.append(f"- Probability above the {label} ({ex['threshold_v_per_m']:g} V/m, {ex['source']}): "
                         f"{ex['probability'] * 100:.1f}% {_ref(field)}")
        lines += [f"- Model: {est['model']}. Calibration: **{est['calibration']}**. {est['averaging_note']}", ""]

    lines += ["## 4. Legal references", ""]
    emf = thresholds.get("emf", {})
    for entry in emf.values():
        lines.append(f"- {entry['value']:g} V/m: {entry['source']} ({entry.get('applies_to', '')})")
    ac = thresholds.get("antenna_context", {})
    lines += [f"- {ac.get('radius_m', '')} m context radius: {ac.get('source', '')}. {ac.get('meaning', '')}",
              f"- Thresholds as of {thresholds.get('as_of', 'n/a')}.", ""]

    lines += ["## 5. Data and provenance", "", "| Tool | Run id | Data kinds |", "|---|---|---|"]
    for run in (located, context, field):
        kinds = ", ".join(f"{k}: {v}" for k, v in sorted(run["data_kinds"].items()))
        lines.append(f"| {run['tool']} | `{run['run_id']}` | {kinds} |")
    lines.append("")
    sources = {s["id"]: s for run in (located, context, field) for s in run["sources"]}
    for source in sources.values():
        lines.append(f"- {source['id']}{' - ' + source['url'] if source.get('url') else ''} "
                     f"(retrieved {source['retrieved_at']})")
    warnings = list(dict.fromkeys(w for run in (located, context, field) for w in run["warnings"]))
    if warnings:
        lines += ["", "**Limits of this report**", ""] + [f"- {w}" for w in warnings]
    return "\n".join(lines) + "\n"
