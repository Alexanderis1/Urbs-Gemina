"""Verifier: a deterministic check that every figure in a draft answer traces to a tool run.

Rules (answer contract, docs/guardrails.md):

* A sentence that contains a number must cite ``[run:<id>]``, ``[src:<url>]`` or ``[data:<manifest id>]``.
* The number must appear in what it cites (rounded to the precision written, percent allowed).
* A cited estimate (a result with ``p50``) needs its range (P5 and P95) and its calibration status.
* A cited synthetic run needs the word "simulated".
* No decision language ("prohibited", "approved", ...): the system supports, the official decides.

It is code, not a model, so it cannot be talked out of a rule.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from agents.config import ROOT, AgentConfig, load_agent_config
from agents.envelope import is_ok

CITATION = re.compile(r"\[(run|src|data):([^\]\s]+)\]")
URL = re.compile(r"https?://\S+")
NUMBER = re.compile(r"(?<![\w.,])[-+]?\d+(?:[.,]\d+)*(\s*%)?")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")
MIN_RUN_PREFIX = 8
#: Keys whose values are identifiers, not figures; their digits must never vouch for a number.
HASH_KEYS = frozenset({"run_id", "sha256", "hash", "snapshot_hash", "url"})


@dataclass(frozen=True)
class Problem:
    code: str
    message: str
    sentence: str = ""


@dataclass
class VerifierReport:
    problems: list[Problem] = field(default_factory=list)
    cited_runs: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _walk_numbers(value: Any) -> Iterator[float]:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        if math.isfinite(value):
            yield float(value)
    elif isinstance(value, str):
        for m in NUMBER.finditer(URL.sub(" ", value)):
            yield from _interpretations(m.group(0).rstrip("% "))
    elif isinstance(value, Mapping):
        for k, v in value.items():
            if k not in HASH_KEYS:
                yield from _walk_numbers(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _walk_numbers(v)


def _readings(token: str) -> list[tuple[float, float]]:
    """Plausible (value, tolerance) readings of a written number.

    "1,4" and "1.4" are 1.4 (to one decimal); "1,234" or "1.234" may be 1234 or 1.234;
    "1.234.567" is Italian thousands. Tolerance is half a unit of the last digit written.
    """
    t = token.strip().lstrip("+-")
    parts = re.split(r"[.,]", t)
    if len(parts) == 1:
        return [(float(t), 0.5)]
    out: list[tuple[float, float]] = []
    if len(parts) == 2:
        out.append((float(parts[0] + "." + parts[1]), 0.5 * 10 ** (-len(parts[1]))))
        if len(parts[1]) == 3:
            out.append((float(parts[0] + parts[1]), 0.5))
        return out
    if all(len(x) == 3 for x in parts[1:]):
        out.append((float("".join(parts)), 0.5))
    out.append((float("".join(parts[:-1]) + "." + parts[-1]), 0.5 * 10 ** (-len(parts[-1]))))
    return out


def _interpretations(token: str) -> list[float]:
    return [v for v, _ in _readings(token)]


def _matches(token: str, is_percent: bool, values: Iterable[float]) -> bool:
    readings = _readings(token)
    for v in values:
        targets = (abs(v), abs(v) * 100.0) if is_percent else (abs(v),)
        for x, tol in readings:
            if any(abs(x - t) <= tol + 1e-9 for t in targets):
                return True
    return False


UNIT_AFTER = re.compile(r"\s*(m|km|metri|metres|meters|v/m)(?![\w/])", re.IGNORECASE)
NAME_KEYS = ("name", "title", "label", "nome")
WORD = re.compile(r"[^\W\d_]{4,}", re.UNICODE)


def _measure_numbers(value: Any, skip: frozenset[str]) -> Iterator[float]:
    """Numeric fields only (no digits inside strings), skipping identifier and count keys."""
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        if math.isfinite(value):
            yield float(value)
    elif isinstance(value, Mapping):
        for k, v in value.items():
            if k not in HASH_KEYS and str(k).lower() not in skip:
                yield from _measure_numbers(v, skip)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _measure_numbers(v, skip)


@dataclass(frozen=True)
class _Record:
    tokens: frozenset[str]
    values: tuple[float, ...]


def _records(value: Any, skip: frozenset[str], generic: frozenset[str], out: list[_Record]) -> None:
    """Named records (a site, a layer hit) with the measurements that belong to them."""
    if isinstance(value, Mapping):
        name = next((value[k] for k in NAME_KEYS if isinstance(value.get(k), str)), None)
        if name:
            toks = frozenset(w.lower() for w in WORD.findall(name) if w.lower() not in generic)
            vals = tuple(_measure_numbers(value, skip))
            if toks and vals:
                out.append(_Record(toks, vals))
        for v in value.values():
            _records(v, skip, generic, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _records(v, skip, generic, out)


def _manifest_sources() -> dict[str, Any]:
    path = ROOT / "data" / "manifest.json"
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    sources = data.get("sources", {})
    return dict(sources) if isinstance(sources, dict) else {}


def _resolve_run(ref: str, runs: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any] | None:
    if len(ref) < MIN_RUN_PREFIX:
        return None
    hits = [r for rid, r in runs.items() if rid.startswith(ref)]
    return hits[0] if len(hits) == 1 else None


def _runs_for_url(url: str, runs: Mapping[str, Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    out = []
    for r in runs.values():
        urls = {str(s.get("url", "")) for s in r.get("sources", [])}
        if url in urls:
            out.append(r)
    return out


def _numbers_for_url(url: str, run: Mapping[str, Any]) -> list[float]:
    """Numbers a URL citation may vouch for: the matching result item if there is one, else the run."""
    items = run.get("result", {}).get("results")
    if isinstance(items, list):
        picked = [i for i in items if isinstance(i, Mapping) and i.get("url") == url]
        if picked:
            dates = [s for s in run.get("sources", []) if isinstance(s, Mapping) and s.get("url") == url]
            return list(_walk_numbers(picked)) + list(_walk_numbers(dates))
    return list(_walk_numbers(run.get("result", {})))


def _contains_any(text: str, words: Iterable[str]) -> bool:
    low = text.lower()
    return any(w.lower() in low for w in words)


def _sentences(text: str, abbreviations: Iterable[str]) -> list[str]:
    """Split into sentences, but not after "art." / "n." / "D.Lgs." and the like."""
    abbr = sorted({a.lower() for a in abbreviations}, key=len, reverse=True)
    guard = "\u2060"
    if abbr:
        pat = re.compile(r"(?<![\w.])(" + "|".join(re.escape(a) for a in abbr) + r")\.\s+", re.IGNORECASE)
        text = pat.sub(lambda m: m.group(1) + "." + guard, text)
    segments: list[str] = []
    for line in text.split("\n"):
        # On one line, a citation covers the uncited sentences just before it (up to the previous
        # citation), so "- Nidi: 0. Dato reale. [run:x]" is one checked unit. Never across lines.
        pending: list[str] = []
        for sent in (x.replace(guard, " ").strip() for x in SENTENCE_SPLIT.split(line)):
            if not sent:
                continue
            pending.append(sent)
            if CITATION.search(sent):
                segments.append(" ".join(pending))
                pending = []
        segments.extend(pending)
    return segments


def verify(text: str, runs: Mapping[str, Mapping[str, Any]], config: AgentConfig | None = None,
           question: str = "") -> VerifierReport:
    """Check a draft. Numbers the officer wrote in ``question`` (an address, a radius) may be echoed."""
    cfg = config or load_agent_config()
    vc = cfg.verifier
    echo = list(_walk_numbers(question))
    skip = frozenset(k.lower() for k in vc.non_measure_keys)
    generic = frozenset(w.lower() for w in vc.generic_name_words) | frozenset(w.lower() for w in WORD.findall(question))
    report = VerifierReport()
    manifest = _manifest_sources()
    cited: dict[str, Mapping[str, Any]] = {}

    low = text.lower()
    for phrase in vc.banned_phrases:
        if phrase.lower() in low:
            report.problems.append(Problem("decision_language", f"uses '{phrase}': the system gives context, the officer decides"))

    for sentence in _sentences(text, vc.abbreviations):
        if not sentence:
            continue
        values: list[float] = []
        measures: list[float] = []
        records: list[_Record] = []
        has_citation = False
        for kind, ref in CITATION.findall(sentence):
            has_citation = True
            if kind == "run":
                run = _resolve_run(ref, runs)
                if run is None:
                    report.problems.append(Problem("unknown_citation", f"run '{ref}' was not produced in this turn", sentence))
                    continue
                cited[str(run["run_id"])] = run
                # A run that is not ok (not available, refused, error) vouches only for its inputs.
                keys = ("inputs", "result", "sources") if is_ok(run) else ("inputs",)
                values.extend(_walk_numbers({k: run.get(k) for k in keys}))
                measures.extend(_measure_numbers({k: run.get(k) for k in keys if k != "sources"}, skip))
                if is_ok(run):
                    _records(run.get("result"), skip, generic, records)
            elif kind == "src":
                matched = _runs_for_url(ref, runs)
                if not matched:
                    report.problems.append(Problem("unknown_citation", f"source '{ref}' was not returned by any tool in this turn", sentence))
                for run in matched:
                    cited[str(run["run_id"])] = run
                    if is_ok(run):
                        url_nums = _numbers_for_url(ref, run)
                        values.extend(url_nums)
                        measures.extend(url_nums)
            else:
                if ref not in manifest:
                    report.problems.append(Problem("unknown_citation", f"dataset '{ref}' is not in data/manifest.json", sentence))
                else:
                    values.extend(_walk_numbers(manifest[ref]))
                    measures.extend(_walk_numbers(manifest[ref]))

        body = CITATION.sub(" ", sentence)
        body = URL.sub(" ", body)
        for pat in vc.exempt_patterns:
            body = re.sub(pat, " ", body, flags=re.IGNORECASE)
        for m in NUMBER.finditer(body):
            token = m.group(0).rstrip("% ").lstrip("+")
            is_percent = bool(m.group(1))
            if echo and _matches(token.lstrip("-"), is_percent, echo):
                continue
            if not has_citation:
                report.problems.append(Problem("uncited_number", f"'{m.group(0).strip()}' has no run id or source", sentence))
            elif not _matches(token.lstrip("-"), is_percent, values):
                report.problems.append(Problem("untraced_number", f"'{m.group(0).strip()}' does not appear in the cited tool output", sentence))
            elif is_percent or UNIT_AFTER.match(body, m.end()):
                # A measurement: it must come from a measured field, not an id or a count...
                tok = token.lstrip("-")
                if not _matches(tok, is_percent, measures):
                    report.problems.append(Problem("untraced_number", f"'{m.group(0).strip()}' matches only an identifier or a count, not a measurement", sentence))
                    continue
                # ...and belong to the site the sentence names, when it names one.
                words = {w.lower() for w in WORD.findall(body)}
                named = [r for r in records if r.tokens & words]
                if named and not any(_matches(tok, is_percent, r.values) for r in named) \
                        and any(_matches(tok, is_percent, r.values) for r in records):
                    report.problems.append(Problem("mismatched_entity", f"'{m.group(0).strip()}' belongs to another site in the tool output", sentence))

    for run in cited.values():
        result = run.get("result", {})
        if isinstance(result, Mapping) and "p50" in result and is_ok(run):
            needed = [result.get("p5"), result.get("p95")]
            nums = [m.group(0).rstrip("% ") for m in NUMBER.finditer(CITATION.sub(" ", text))]
            for v in needed:
                if isinstance(v, (int, float)) and not any(_matches(n.lstrip("-+"), False, [float(v)]) for n in nums):
                    report.problems.append(Problem("missing_range", f"estimate from {run['tool']} must show P5 and P95"))
                    break
            if not _contains_any(text, vc.calibration_words):
                report.problems.append(Problem("missing_calibration", f"estimate from {run['tool']} must say calibrated or uncalibrated"))
            if not _contains_any(text, vc.estimate_words):
                report.problems.append(Problem("missing_estimate_label", "say it is an estimate, not a measurement"))
        if run.get("synthetic") is True and not _contains_any(text, vc.simulated_words):
            report.problems.append(Problem("missing_simulated_label", f"{run['tool']} used simulated data; say so"))

    report.cited_runs = list(cited)
    return report


def _line_numbers(line: str, cfg: AgentConfig, echo: list[float]) -> list[tuple[str, bool]]:
    body = URL.sub(" ", line)
    for pat in cfg.verifier.exempt_patterns:
        body = re.sub(pat, " ", body, flags=re.IGNORECASE)
    out = []
    for m in NUMBER.finditer(body):
        token = m.group(0).rstrip("% ").lstrip("+-")
        pct = bool(m.group(1))
        if not (echo and _matches(token, pct, echo)):
            out.append((token, pct))
    return out


def _exact(token: str, is_percent: bool, values: Iterable[float]) -> bool:
    readings = [x for x, _ in _readings(token)]
    for v in values:
        targets = (abs(v), abs(v) * 100.0) if is_percent else (abs(v),)
        if any(abs(x - t) < 1e-9 for x in readings for t in targets):
            return True
    return False


def auto_cite(text: str, runs: Mapping[str, Mapping[str, Any]], config: AgentConfig | None = None,
              question: str = "") -> str:
    return auto_cite_marked(text, runs, config, question)[0]


def auto_cite_marked(text: str, runs: Mapping[str, Mapping[str, Any]], config: AgentConfig | None = None,
                     question: str = "") -> tuple[str, list[int]]:
    """Like ``auto_cite``, also returning the indexes of the lines that code cited (cite_mode "auto")."""
    """Attach a citation, by code, to a line that has figures but no citation, when one tool run of
    this turn contains every figure on that line. Figures found in no tool output stay uncited, so
    the verifier still blocks them: this fixes layout (headings, bullets), never content."""
    cfg = config or load_agent_config()
    echo = list(_walk_numbers(question))
    ok_runs = [r for r in runs.values() if is_ok(r)]
    pools = [(str(r["run_id"]), list(_walk_numbers({k: r.get(k) for k in ("inputs", "result", "sources")}))) for r in ok_runs]
    out_lines: list[str] = []
    marked: list[int] = []
    for idx, line in enumerate(text.split("\n")):
        nums = _line_numbers(CITATION.sub(" ", line), cfg, echo)
        if nums and not CITATION.search(line):
            hits = [(sum(_exact(t, pct, vals) for t, pct in nums), i, rid) for i, (rid, vals) in enumerate(pools)
                    if all(_matches(t, pct, vals) for t, pct in nums)]
            if hits:
                best = max(hits)  # most figures written exactly as in the tool output, then the latest run
                line = line.rstrip() + f" [run:{best[2][:12]}]"
                marked.append(idx)
        out_lines.append(line)
    return "\n".join(out_lines), marked


def citation_trace(text: str, runs: Mapping[str, Mapping[str, Any]], auto_lines: Iterable[int]) -> list[dict[str, Any]]:
    """One entry per citation in the final text: line, cited run or source, and cite_mode explicit|auto."""
    auto = set(auto_lines)
    out: list[dict[str, Any]] = []
    for idx, line in enumerate(text.split("\n")):
        for n, (kind, ref) in enumerate(CITATION.findall(line)):
            run = _resolve_run(ref, runs) if kind == "run" else None
            mode = "auto" if idx in auto and n == len(CITATION.findall(line)) - 1 else "explicit"
            out.append({"line": idx, "kind": kind, "ref": str(run["run_id"]) if run else ref, "cite_mode": mode})
    return out


def describe_problems(report: VerifierReport) -> str:
    return "\n".join(f"- {p.code}: {p.message}" + (f' (in: "{p.sentence}")' if p.sentence else "") for p in report.problems)
