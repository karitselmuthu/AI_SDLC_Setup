"""Waivers: the tech lead's recorded, temporary, second-approved decision on Critical and High review findings, and how the Release gate treats them."""
import datetime
import json

import pytest

from architect import baseline
from review import agent as R
from release import agent as RL
from test_release import rl, sib, text as rtext  # noqa: F401
from test_review import rv, chain  # noqa: F401

REASON = "The finding is in a feature flag that stays off until the fix ships next sprint, and monitoring alerts on any use of it."
TODAY = datetime.date(2026, 11, 24)
REPORT = ("# Review report\n## Scorecard\nRouted for human disposition: 2.\n## Routed for human disposition (Critical and High findings still standing)\n"
          "- **C1** (High, Confirmed, S): a behaviour | impact | src/app.py:2\n- **Scanner** (Critical) `src/new.py:1`: secret, key in code\n## Review coverage\nx\n")


@pytest.fixture
def wv(rv, tmp_path, monkeypatch):
    monkeypatch.setattr(R, "today", lambda: TODAY)
    s = dict(rv, asked=[], second=True, tmp=tmp_path)
    monkeypatch.setattr(R, "approve", lambda who: s["asked"].append(who) or s["second"])
    chain(rv)
    R.run_report()
    return s


def entries(*items):
    return [dict(finding=f, decision=d, reason=REASON, **({"expires": e} if e else {})) for f, d, e in items]


def file(wv, data):
    p = wv["tmp"] / "disp.json"
    p.write_text(json.dumps(data))
    return str(p)


def record(wv):
    return (wv["briefs"] / "disposition-record.md").read_text()


def test_the_routed_list_is_read_from_the_report_and_names_scanner_findings(wv):
    rep = (wv["briefs"] / "review-report.md").read_text()
    assert R.routed(rep) == [("C1", "High"), ("Scanner src/new.py:1", "Critical")] and R.routed(REPORT) == R.routed(rep)


def test_the_step_exists_needs_the_report_and_no_repository():
    assert list(R.STEPS)[-1] == "disposition" and "disposition" not in R.NEEDS_REPO and R.STEPS["disposition"][2] == [R.DISPOSITION] and R.STEPS["disposition"][3] == ["review-report.md"]


def test_a_waiver_needs_a_reason_a_future_expiry_within_the_limit_and_names_a_routed_finding():
    ok = dict(decision="waive", reason=REASON, expires="2026-12-01")
    assert R.check_entry(ok, "High") == "" and R.check_entry(dict(ok, decision="fix"), "High") == ""
    assert "decision must be" in R.check_entry(dict(ok, decision="ignore"), "High")
    assert "at least 12 words" in R.check_entry(dict(ok, reason="it is fine"), "High")
    assert "expiry date (YYYY-MM-DD)" in R.check_entry({k: v for k, v in ok.items() if k != "expires"}, "High")
    assert "not in the future" in R.check_entry(dict(ok, expires="2026-11-24"), "High")
    assert "at most 30 days" in R.check_entry(dict(ok, expires="2027-01-30"), "High") and "at most 14 days" in R.check_entry(dict(ok, expires="2026-12-20"), "Critical")


def test_a_high_waiver_is_recorded_without_a_second_approver_and_a_critical_one_needs_one(wv):
    R.today = lambda: TODAY
    R.run_disposition(file(wv, entries(("C1", "waive", "2026-12-10"), ("Scanner src/new.py:1", "waive", "2026-12-05"))))
    t = record(wv)
    assert "| C1 | High | waive | 2026-12-10 | No |" in t and "| Scanner src/new.py:1 | Critical | waive | 2026-12-05 | Yes |" in t and "**2 of 2 finding(s) have a decision; 2 waived.**" in t
    assert len(wv["asked"]) == 1 and wv["asked"][0].startswith("Release manager accepts the residual risk of the Critical finding Scanner src/new.py:1")
    d = json.loads((wv["briefs"] / "dispositions.json").read_text())
    assert d["report_sha256"] == baseline.sha256(wv["briefs"] / "review-report.md") and [e["second_approval"] for e in d["entries"]] == [False, True]
    assert not baseline.problems(wv["briefs"], {"disposition": R.STEPS["disposition"]})


def test_a_critical_waiver_the_second_approver_declines_is_not_accepted(wv):
    wv["second"] = False
    R.run_disposition(file(wv, entries(("C1", "fix", None), ("Scanner src/new.py:1", "waive", "2026-12-05"))))
    t = record(wv)
    assert "the second approver did not accept the risk of a Critical waiver" in t and "1 still need one: Scanner src/new.py:1" in t
    assert [e["finding"] for e in json.loads((wv["briefs"] / "dispositions.json").read_text())["entries"]] == ["C1"]


def test_bad_entries_are_listed_not_hidden_and_unlisted_findings_stay_undecided(wv):
    R.run_disposition(file(wv, entries(("ZZ9", "waive", "2026-12-01"), ("C1", "waive", "2027-06-01"), ("C1", "fix", None))))
    t = record(wv)
    assert "ZZ9: this finding is not routed" in t and "C1: a waiver of a High finding can last at most 30 days" in t and "C1: it already has a decision" in t
    assert "**0 of 2 finding(s) have a decision; 0 waived.** 2 still need one" in t


def test_the_step_refuses_without_a_file_or_with_one_that_is_not_json(wv):
    with pytest.raises(SystemExit, match="pass --dispositions"):
        R.run_disposition(None)
    bad = wv["tmp"] / "bad.json"
    bad.write_text("not json")
    with pytest.raises(SystemExit, match="must be JSON"):
        R.run_disposition(str(bad))


def test_it_cannot_run_before_the_report_is_approved(rv):
    with pytest.raises(SystemExit, match="Cannot disposition"):
        R.run_disposition(None)


# ---- the Release gate ---------------------------------------------------------------------------------------------------------

def waiver_files(rl, entries_, expires="2026-12-01", approved=True, report=REPORT):
    ws = rl["ws"]
    sib(ws, "review", RV_, "review-report.md", report)
    b = ws / "review/briefs"
    (b / "dispositions.json").write_text(json.dumps(dict(report_sha256=baseline.sha256(b / "review-report.md"), entries=[dict(finding=f, severity="High", decision=d, reason=REASON, expires=expires, second_approval=False) for f, d in entries_])))
    if approved:
        sib(ws, "review", RV_, "disposition-record.md", "record")


RV_ = R


def gate(rl):
    return {x[0]: x for x in RL.gates(rl["briefs"])}["Code review complete, no open high-risk finding"]


def test_routed_findings_block_the_gate_until_every_one_has_a_valid_approved_waiver(rl):
    RL.run_step("request", [str(rl["req"])])
    waiver_files(rl, [("C1", "waive"), ("Scanner src/new.py:1", "waive")])
    g = gate(rl)
    assert g[1] == "MET" and "2 finding(s) waived by the tech lead, valid until 2026-12-01" in g[2] and "Waived, not fixed" in g[2]
    waiver_files(rl, [("C1", "waive")])
    assert gate(rl)[1] == "UNMET" and "Scanner src/new.py:1 has no decision" in gate(rl)[2]


def test_fix_and_defer_never_clear_the_gate(rl):
    RL.run_step("request", [str(rl["req"])])
    waiver_files(rl, [("C1", "fix"), ("Scanner src/new.py:1", "defer")])
    g = gate(rl)
    assert g[1] == "UNMET" and "C1 is 'fix', not waived" in g[2] and "Scanner src/new.py:1 is 'defer'" in g[2]


def test_an_expired_waiver_stops_covering_the_finding(rl):
    RL.run_step("request", [str(rl["req"])])
    waiver_files(rl, [("C1", "waive"), ("Scanner src/new.py:1", "waive")], expires="2026-11-23")
    assert gate(rl)[1] == "UNMET" and "waiver expired on 2026-11-23" in gate(rl)[2]


def test_a_waiver_is_void_when_the_review_report_changes_or_the_record_is_not_approved(rl):
    RL.run_step("request", [str(rl["req"])])
    waiver_files(rl, [("C1", "waive"), ("Scanner src/new.py:1", "waive")])
    b = rl["ws"] / "review/briefs"
    (b / "review-report.md").write_text(REPORT + "\nedited after the waivers were approved\n")
    assert gate(rl)[1] == "UNMET"
    waiver_files(rl, [("C1", "waive"), ("Scanner src/new.py:1", "waive")], approved=False)
    (b / "disposition-record.md").unlink(missing_ok=True)
    assert gate(rl)[1] == "UNMET" and "no approved waiver covers them" in gate(rl)[2]


def test_with_nothing_routed_the_gate_needs_no_waiver(rl):
    RL.run_step("request", [str(rl["req"])])
    assert gate(rl)[1] == "MET" and "none routed" in gate(rl)[2]
