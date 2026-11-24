"""SRE evidence: parsing, freshness and the reliability arithmetic. No model, no network."""
from datetime import datetime, timedelta, timezone

from sre import evidence as E

T0 = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)
T = lambda m: T0 + timedelta(minutes=m)
SLO = dict(id="SLO1", metric="success_ratio", kind="success_ratio", objective=99.9, window_h=720.0)


def ev(series=None, events=()):
    return dict(series=series or {}, events=list(events), logs=[], bad=0)


def ratio(values, step=5):
    return [(T(i * step), v) for i, v in enumerate(values)]


def test_files_are_parsed_and_unusable_rows_are_counted_not_guessed(tmp_path):
    (tmp_path / "m.csv").write_text("time,metric,value\n2026-11-24T09:00:00Z,error_rate,0.01\nnot-a-time,error_rate,1\n2026-11-24T09:05:00Z,error_rate,abc\n2026-11-24 09:10:00,latency_ms,250\n")
    (tmp_path / "e.jsonl").write_text('{"time":"2026-11-24T09:02:00Z","kind":"deploy","name":"v2","message":"rollout"}\nnot json\n{"time":"2026-11-24T09:01:00Z","kind":"alert","name":"A"}\n')
    (tmp_path / "l.txt").write_text("2026-11-24T09:03:00Z ERROR upstream timeout\nplain line without time\n2026-11-24 09:04:00 WARN slow\n")
    d = E.load(dict(metrics=[tmp_path / "m.csv"], events=[tmp_path / "e.jsonl"], logs=[tmp_path / "l.txt"]))
    assert d["bad"] == 2 and set(d["series"]) == {"error_rate", "latency_ms"} and d["series"]["latency_ms"][0][0].tzinfo is not None  # naive times are read as UTC
    assert [e["id"] for e in d["events"]] == ["EV1", "EV2"] and d["events"][0]["name"] == "A"  # ids follow time order
    assert [x["id"] for x in d["logs"]] == ["L1", "L3"]  # the id is the line number
    assert E.valid_ids(d) >= {"M:error_rate", "EV1", "L3"} and "L2" not in E.valid_ids(d)


def test_freshness_says_fresh_stale_or_no_data():
    d = ev({"m": ratio([1, 1])})
    assert E.freshness(d, T(7), 15) == (2.0, "fresh") and E.freshness(d, T(60), 15)[1] == "STALE" and E.freshness(ev(), T(0), 15) == (None, "NO DATA")


def test_durations_and_objectives_are_read_from_how_people_write_them():
    assert E.duration_hours("30d") == 720 and E.duration_hours("5 min") == 5 / 60 and E.duration_hours("2 hours") == 2 and E.duration_hours("1w") == 168 and E.duration_hours("soon") is None
    assert E.objective("99.9%") == 99.9 and E.objective("p95 under 300 ms") == 95.0 or E.objective("300 ms") == 300.0


def test_burn_rate_is_the_error_ratio_over_the_error_budget():
    assert round(E.burn_rate(0.01, 99.9), 6) == 10.0 and round(E.burn_rate(0.0005, 99.9), 6) == 0.5 and E.burn_rate(0.01, 100.0) is None
    assert round(E.as_error_ratio("success_ratio", [0.99, 0.99]), 6) == 0.01 and round(E.as_error_ratio("error_rate", [1.0, 3.0]), 6) == 0.02 and E.as_error_ratio("error_rate", [1.0]) == 1.0  # values above 1 are percentages
    assert E.as_error_ratio("error_rate", []) is None


def test_a_series_is_a_ratio_or_a_percentage_as_a_whole_never_value_by_value():
    assert E.is_pct([(T(0), 0.5), (T(5), 2.0)]) is True and E.is_pct([(T(0), 0.5), (T(5), 1.0)]) is False
    assert round(E.as_error_ratio("error_rate", [1.0, 3.0], pct=True), 6) == 0.02 and E.as_error_ratio("error_rate", [1.0, 0.5], pct=False) == 0.75


def test_a_fast_burn_pages_a_slow_burn_tickets_and_a_mild_one_is_only_watched():
    ten = E.detect(ev({"success_ratio": ratio([0.99] * 13)}), [SLO], [], T(60), True)
    assert ten[0]["priority"] == "Ticket" and "10.0x" in ten[0]["signal"]  # 10x is above the 6x slow-burn line but below the 14.4x page line
    page = E.detect(ev({"success_ratio": ratio([0.98] * 13)}), [SLO], [], T(60), True)
    assert page[0]["priority"] == "Page" and "20.0x" in page[0]["signal"] and page[0]["evidence"] == ["M:success_ratio"] and page[0]["confidence"] == "High" and page[0]["id"] == "R1"
    # healthy for the last hour, but 7x burn over the last 6 hours (ticket) then 1.5x (watch)
    slow = [(T(i * 10), 0.993 if i < 24 else 0.9999) for i in range(36)]
    t = E.detect(ev({"success_ratio": slow}), [SLO], [], T(350), True)
    assert t and t[0]["priority"] in ("Ticket", "Watch")
    watch = E.detect(ev({"success_ratio": ratio([0.9985] * 13)}), [SLO], [], T(60), True)
    assert watch[0]["priority"] == "Watch" and "1.5x" in watch[0]["signal"]
    assert E.detect(ev({"success_ratio": ratio([0.9999] * 13)}), [SLO], [], T(60), True) == []


def test_stale_or_sparse_data_lowers_confidence_and_a_missing_metric_is_a_gap_not_health():
    assert E.detect(ev({"success_ratio": ratio([0.99] * 13)}), [SLO], [], T(60), False)[0]["confidence"] == "Low"
    assert E.detect(ev({"success_ratio": ratio([0.99, 0.99])}), [SLO], [], T(5), True)[0]["confidence"] == "Low"
    gap = E.detect(ev(), [SLO], [], T(60), True)
    assert gap[0]["kind"] == "gap" and "no data for metric success_ratio" in gap[0]["signal"]


def test_latency_and_capacity_risks():
    lat = dict(id="SLO2", metric="latency_p95_ms", kind="latency_ms", objective=300.0, window_h=720.0)
    r = E.detect(ev({"latency_p95_ms": ratio([900, 950, 980, 1000, 990, 970, 900, 910, 920, 930, 940, 950, 960])}), [lat], [], T(60), True)
    assert r[0]["priority"] == "Page" and "100%" in r[0]["signal"]
    sat = dict(id="SLO3", metric="cpu", kind="saturation", objective=80.0, window_h=1.0)
    c = E.detect(ev({"cpu": [(T(i * 30), 50 + i * 12) for i in range(5)]}), [sat], [], T(120), True)
    assert c[0]["kind"] == "capacity" and "full in about" in c[0]["signal"] and c[0]["priority"] == "Page"


def test_alert_rules_fire_only_when_every_sample_in_the_for_window_meets_the_condition():
    rule = dict(name="HighErrors", metric="error_rate", op=">", value=0.05, for_min=10.0, severity="page")
    bad = ev({"error_rate": ratio([0.2, 0.3, 0.4, 0.5])})
    assert E.rule_firing(rule, bad["series"], T(15))[0] is True
    ok = ev({"error_rate": ratio([0.2, 0.01, 0.4, 0.5])})
    assert E.rule_firing(rule, ok["series"], T(15))[0] is False and E.rule_firing(rule, {"error_rate": [(T(0), 0.9)]}, T(0))[0] is False
    r = E.detect(bad, [], [rule], T(15), True)
    assert r[0]["kind"] == "alert" and r[0]["priority"] == "Page"


def test_the_same_alert_three_times_in_a_day_is_a_recurring_signal():
    events = [dict(id=f"EV{i}", t=T(i * 60), kind="alert", name="DiskFull", message="") for i in range(1, 4)]
    r = E.detect(ev(events=events), [], [], T(240), True)
    assert r[0]["kind"] == "recurring" and r[0]["evidence"] == ["EV1", "EV2", "EV3"] and r[0]["priority"] == "Watch"
