"""Height agreement metrics for the honesty panel."""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Optional, Sequence


@dataclass(frozen=True)
class HeightAgreement:
    source: str
    n: int
    bias_m: Optional[float]
    mae_m: Optional[float]
    rmse_m: Optional[float]
    share_within: Optional[float]
    within_m: float
    reference: str = "osm_tag"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ok(v: Optional[float]) -> bool:
    return v is not None and math.isfinite(v)


def compare_heights(
    pred: Sequence[Optional[float]],
    ref: Sequence[Optional[float]],
    *,
    source: str,
    within_m: float,
    reference: str = "osm_tag",
) -> HeightAgreement:
    """Compare predicted heights with reference heights where both exist. bias = mean(pred - ref)."""
    diffs = [float(p) - float(r) for p, r in zip(pred, ref) if _ok(p) and _ok(r)]  # type: ignore[arg-type]
    n = len(diffs)
    if n == 0:
        return HeightAgreement(source, 0, None, None, None, None, within_m, reference)
    return HeightAgreement(
        source=source,
        n=n,
        bias_m=sum(diffs) / n,
        mae_m=sum(abs(d) for d in diffs) / n,
        rmse_m=math.sqrt(sum(d * d for d in diffs) / n),
        share_within=sum(1 for d in diffs if abs(d) <= within_m) / n,
        within_m=within_m,
        reference=reference,
    )


def class_agreement(
    pred: Sequence[Optional[float]],
    low: Sequence[Optional[float]],
    high: Sequence[Optional[float]],
    *,
    source: str,
) -> HeightAgreement:
    """Share of buildings whose height falls inside the reference height class [low, high].

    Bias and errors are measured to the nearest class edge (0 when inside).
    """
    diffs: list[float] = []
    for p, lo, hi in zip(pred, low, high):
        if not (_ok(p) and _ok(lo) and _ok(hi)):
            continue
        pv, lv, hv = float(p), float(lo), float(hi)  # type: ignore[arg-type]
        diffs.append(pv - hv if pv > hv else pv - lv if pv < lv else 0.0)
    n = len(diffs)
    if n == 0:
        return HeightAgreement(source, 0, None, None, None, None, 0.0, "raster_class")
    return HeightAgreement(
        source=source,
        n=n,
        bias_m=sum(diffs) / n,
        mae_m=sum(abs(d) for d in diffs) / n,
        rmse_m=math.sqrt(sum(d * d for d in diffs) / n),
        share_within=sum(1 for d in diffs if d == 0.0) / n,
        within_m=0.0,
        reference="raster_class",
    )


def source_shares(sources: Iterable[str]) -> dict[str, float]:
    counts = Counter(sources)
    total = sum(counts.values())
    return {k: v / total for k, v in counts.items()} if total else {}


def render_report(
    n_buildings: int, shares: dict[str, float], agreements: Sequence[HeightAgreement], notes: Sequence[str]
) -> str:
    """Plain Markdown report, readable by a non-specialist."""
    lines = ["# City model G0: height check", "", f"Buildings in the model: **{n_buildings:,}**", ""]
    lines += ["## Where each height comes from", "", "| Source | Share of buildings |", "|---|---|"]
    lines += [f"| {k} | {v:.1%} |" for k, v in sorted(shares.items(), key=lambda kv: -kv[1])]
    lines += ["", "## How well the height sources agree", ""]
    lines += [
        "Bias above zero means the source is taller than the reference.",
        "",
        "| Source | Reference | Buildings compared | Bias (m) | Mean error (m) | RMSE (m) | Within tolerance |",
        "|---|---|---|---|---|---|---|",
    ]
    for a in agreements:
        if a.n == 0 or a.bias_m is None or a.mae_m is None or a.rmse_m is None or a.share_within is None:
            lines.append(f"| {a.source} | {a.reference} | 0 | - | - | - | - |")
        else:
            lines.append(
                f"| {a.source} | {a.reference} | {a.n:,} | {a.bias_m:+.1f} | {a.mae_m:.1f} | {a.rmse_m:.1f} "
                + (f"| {a.share_within:.0%} inside the class |" if a.reference == "raster_class"
                   else f"| {a.share_within:.0%} within {a.within_m:g} m |")
            )
    lines += ["", "## Notes", ""] + [f"- {n}" for n in notes]
    return "\n".join(lines) + "\n"
