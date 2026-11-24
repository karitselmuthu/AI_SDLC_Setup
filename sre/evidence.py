"""SRE evidence: read-only operational snapshots and the reliability arithmetic on them. Plain code, no model, no network, nothing is written.
Formats (all times ISO-8601, UTC when no offset is given):
  metrics.csv   time,metric,value        ratios (error_rate, success_ratio) are 0..1, a value above 1 is read as a percentage
  events.jsonl  one JSON object per line: {"time", "kind": deploy|alert|config|incident|note, "name", "message"}
  logs.txt      lines that start with an ISO time, then text; lines without one are ignored
Evidence ids a record may cite: M:<metric>, EV<n> (n-th event), L<n> (line n of the log), R<n> (a detected risk).
"""
import csv
import json
import re
import statistics
from datetime import datetime, timedelta, timezone

KINDS = ("error_rate", "success_ratio", "latency_ms", "saturation")
PAGE_BURN, TICKET_BURN = (1.0, 14.4), (6.0, 6.0)  # (window hours, burn rate): the usual multi-window fast and slow burn thresholds
ID = re.compile(r"\b(EV\d+|L\d+|R\d+|M:[A-Za-z0-9_.:-]+)")


def ts(text):
    t = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def parse_metrics(path):
    """({metric: [(time, value)] sorted}, rows skipped because they were not time,metric,value)."""
    series, bad = {}, 0
    with open(path, newline="", errors="ignore") as f:
        for row in csv.DictReader(f):
            try:
                series.setdefault(row["metric"].strip(), []).append((ts(row["time"]), float(row["value"])))
            except (KeyError, ValueError, TypeError, AttributeError):
                bad += 1
    return {k: sorted(v) for k, v in series.items()}, bad


def parse_events(path):
    out = []
    for n, line in enumerate(open(path, errors="ignore").read().splitlines(), 1):
        try:
            d = json.loads(line)
            out.append(dict(id=f"EV{len(out) + 1}", t=ts(d["time"]), kind=str(d.get("kind", "note")), name=str(d.get("name", "")), message=str(d.get("message", "")), line=n))
        except (ValueError, KeyError, TypeError):
            continue
    return out


def parse_logs(path):
    out = []
    for n, line in enumerate(open(path, errors="ignore").read().splitlines(), 1):
        m = re.match(r"\s*(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)\s*(.*)", line)
        if m:
            try:
                out.append(dict(id=f"L{n}", t=ts(m.group(1)), text=m.group(2)))
            except ValueError:
                continue
    return out


def load(paths):
    """paths: dict(metrics=[...], events=[...], logs=[...]) -> dict(series, events, logs, bad)."""
    series, events, logs, bad = {}, [], [], 0
    for p in paths.get("metrics", []):
        s, b = parse_metrics(p)
        bad += b
        for k, v in s.items():
            series[k] = sorted(series.get(k, []) + v)
    for p in paths.get("events", []):
        events += parse_events(p)
    for p in paths.get("logs", []):
        logs += parse_logs(p)
    events = [dict(e, id=f"EV{i}") for i, e in enumerate(sorted(events, key=lambda e: e["t"]), 1)]
    return dict(series=series, events=events, logs=sorted(logs, key=lambda x: x["t"]), bad=bad)


def valid_ids(ev):
    return {f"M:{k}" for k in ev["series"]} | {e["id"] for e in ev["events"]} | {x["id"] for x in ev["logs"]}


def newest(ev):
    times = [v[-1][0] for v in ev["series"].values() if v] + [e["t"] for e in ev["events"]] + [x["t"] for x in ev["logs"]]
    return max(times) if times else None


def freshness(ev, now, max_age_min):
    t = newest(ev)
    if t is None:
        return None, "NO DATA"
    age = (now - t).total_seconds() / 60
    return round(age, 1), ("fresh" if age <= max_age_min else "STALE")


def duration_hours(text):
    m = re.search(r"(\d+(?:\.\d+)?)\s*(m|min|minutes?|h|hours?|d|days?|w|weeks?)\b", str(text).strip(), re.I)
    if not m:
        return None
    n, u = float(m.group(1)), m.group(2).lower()
    return n / 60 if u.startswith("m") else n if u.startswith("h") else n * 24 if u.startswith("d") else n * 168


def objective(text):
    m = re.search(r"-?\d+(?:\.\d+)?", str(text))
    return float(m.group(0)) if m else None


def points(series, end, hours):
    return [(t, v) for t, v in series if end - timedelta(hours=hours) < t <= end]


def is_pct(series):
    """A whole series is read as percentages when any value in it is above 1; decided once per series so a single 1.0 is never read two ways."""
    return any(v > 1 for _, v in series)


def as_error_ratio(kind, values, pct=None):
    """Mean error ratio 0..1 from the values of an error_rate or success_ratio metric. pct says the values are percentages (default: any value above 1)."""
    if not values:
        return None
    pct = any(x > 1 for x in values) if pct is None else pct
    m = statistics.fmean(x / 100 if pct else x for x in values)
    return m if kind == "error_rate" else 1 - m


def burn_rate(error_ratio, target_pct):
    budget = 1 - target_pct / 100
    return error_ratio / budget if budget > 0 and error_ratio is not None else None


def confidence(n, fresh, agree=True):
    if not fresh or n < 3:
        return "Low"
    return "High" if n >= 6 and agree else "Medium"


def cond_ok(op, a, b):
    return {">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b, "==": a == b}[op]


def rule_firing(rule, series, end, cadence_min=1.0):
    """rule: dict(metric, op, value, for_min). Firing when every sample in the last for_min minutes meets the condition (and there are at least two)."""
    pts = [(t, v) for t, v in series.get(rule["metric"], []) if end - timedelta(minutes=max(rule["for_min"], cadence_min)) <= t <= end]
    return len(pts) >= 2 and all(cond_ok(rule["op"], v, rule["value"]) for _, v in pts), pts


def trend_per_hour(pts):
    if len(pts) < 2:
        return 0.0
    (t0, v0), (t1, v1) = pts[0], pts[-1]
    hours = (t1 - t0).total_seconds() / 3600
    return (v1 - v0) / hours if hours else 0.0


def detect(ev, slos, rules, end, fresh):
    """Reliability risks by the rules in the service context. Each: dict(kind, signal, evidence, impact, confidence, priority). Priority: Page, Ticket or Watch."""
    out = []
    for s in slos:  # s: dict(id, metric, kind, objective, window_h)
        series = ev["series"].get(s["metric"], [])
        if not series:
            out.append(dict(kind="gap", signal=f"{s['id']}: no data for metric {s['metric']}", evidence=[], impact="the objective cannot be evaluated", confidence="Low", priority="Watch"))
            continue
        if s["kind"] in ("error_rate", "success_ratio"):
            burns = {}
            for h in (PAGE_BURN[0], TICKET_BURN[0], min(s["window_h"], 24.0)):
                pts = points(series, end, h)
                burns[h] = (burn_rate(as_error_ratio(s["kind"], [v for _, v in pts], is_pct(series)), s["objective"]), len(pts))
            b1, n1 = burns[PAGE_BURN[0]]
            b6, n6 = burns[TICKET_BURN[0]]
            if b1 is not None and b1 >= PAGE_BURN[1]:
                pri, h, b, n = "Page", PAGE_BURN[0], b1, n1
            elif b6 is not None and b6 >= TICKET_BURN[1]:
                pri, h, b, n = "Ticket", TICKET_BURN[0], b6, n6
            else:
                top = max(((b, h, n) for h, (b, n) in burns.items() if b is not None), default=None)
                if not top or top[0] < 1:
                    continue
                b, h, n = top
                pri = "Watch"
            agree = (b6 or 0) >= 1 and (b1 or 0) >= 1
            out.append(dict(kind="burn", signal=f"{s['id']}: burn rate {b:.1f}x over {h:g}h", evidence=[f"M:{s['metric']}"],
                            impact=f"Burning the {s['window_h']:g}h error budget {b:.1f}x faster than allowed; at this rate it is gone in {s['window_h'] / b:.1f} hours",
                            confidence=confidence(n, fresh, agree), priority=pri))
        elif s["kind"] == "latency_ms":
            pts = points(series, end, 1.0)
            over = [v for _, v in pts if v > s["objective"]]
            if pts and over:
                share = len(over) / len(pts)
                out.append(dict(kind="latency", signal=f"{s['id']}: latency above {s['objective']:g} ms in {share:.0%} of the last hour", evidence=[f"M:{s['metric']}"],
                                impact=f"worst sample {max(over):g} ms against an objective of {s['objective']:g} ms", confidence=confidence(len(pts), fresh), priority="Page" if share >= 0.5 and len(pts) >= 3 else "Ticket"))
        elif s["kind"] == "saturation":
            pts = points(series, end, 6.0)
            if pts:
                last, slope = pts[-1][1], trend_per_hour(pts)
                limit = 100.0 if max(v for _, v in pts) > 1 else 1.0
                eta = (limit - last) / slope if slope > 0 else None
                if last > s["objective"] or (eta is not None and eta < 4):
                    out.append(dict(kind="capacity", signal=f"{s['id']}: saturation {last:g} against {s['objective']:g}" + (f", full in about {eta:.1f} hours" if eta is not None and eta < 24 else ""),
                                    evidence=[f"M:{s['metric']}"], impact="capacity pressure; latency and errors usually follow", confidence=confidence(len(pts), fresh),
                                    priority="Page" if eta is not None and eta < 1 else "Ticket"))
    for r in rules:  # r: dict(name, metric, op, value, for_min, severity)
        firing, pts = rule_firing(r, ev["series"], end)
        if firing:
            out.append(dict(kind="alert", signal=f"alert rule {r['name']} is firing ({r['metric']} {r['op']} {r['value']:g} for {r['for_min']:g} min)", evidence=[f"M:{r['metric']}"],
                            impact=f"configured severity: {r['severity']}", confidence=confidence(len(pts), fresh), priority="Page" if re.search(r"(?i)page|crit|sev ?[01]", r["severity"]) else "Ticket"))
    names = {}
    for e in ev["events"]:
        if e["kind"] == "alert" and end - timedelta(hours=24) < e["t"] <= end:
            names.setdefault(e["name"], []).append(e["id"])
    for n, ids in names.items():
        if len(ids) >= 3:
            out.append(dict(kind="recurring", signal=f"alert '{n}' fired {len(ids)} times in 24h", evidence=ids[:6], impact="a recurring signal usually means an unfixed cause or a noisy rule", confidence="Medium" if fresh else "Low", priority="Watch"))
    order = {"Page": 0, "Ticket": 1, "Watch": 2}
    out.sort(key=lambda r: (order[r["priority"]], {"High": 0, "Medium": 1, "Low": 2}[r["confidence"]]))
    for i, r in enumerate(out, 1):
        r["id"] = f"R{i}"
    return out
