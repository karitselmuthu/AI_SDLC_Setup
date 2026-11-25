"""AWS Lambda release profile. A stand-in `aws` program on PATH plays the service, so nothing here touches a real account; a live trial is still to be done."""
import json
import stat
import sys

import pytest

from release import aws as AWS
from release import agent as RL
from test_release import rl, plan, run, text, CROSS  # noqa: F401

PROFILE = dict(service="lambda", account_id="123456789012", region="eu-west-1", function="orders-api", alias="live", previous_alias="previous", package="dist/app.zip",
               alarm="orders-errors", smoke_payload="{}")
FAKE = '''#!{py}
import json, os, sys
st_file, log = os.environ["FAKE_STATE"], os.environ["FAKE_LOG"]
st = json.load(open(st_file))
a = sys.argv[1:]
open(log, "a").write(" ".join(a) + "\\n")
arg = lambda n: a[a.index(n) + 1] if n in a else None
def out(v): print(v); save(); sys.exit(0)
def save(): json.dump(st, open(st_file, "w"))
def fail(m): sys.stderr.write(m + "\\n"); sys.exit(255)
if a[0] == "sts":
    acct = os.environ.get("FAKE_ACCOUNT", "")
    out(acct) if acct else fail("Your session has expired. Please reauthenticate.")
if a[0] == "cloudwatch":
    out(st["alarm"])
cmd = a[1]
if cmd == "get-alias":
    n = arg("--name")
    out(st["aliases"][n]) if n in st["aliases"] else fail("ResourceNotFoundException: alias " + n)
if cmd == "list-versions-by-function": out(st["versions"][-1])
if cmd == "update-function-code": st["code"] = a; out("{}")
if cmd == "wait": out("")
if cmd == "publish-version":
    st["versions"].append(str(len(st["versions"]))); out(json.dumps({"Version": st["versions"][-1]}))
if cmd == "update-alias": st["aliases"][arg("--name")] = arg("--function-version"); out("{}")
if cmd == "get-function-configuration": out(st["status"])
if cmd == "invoke": out(st["invoke"])
fail("unexpected: " + " ".join(a))
'''


@pytest.fixture
def aws(rl, tmp_path, monkeypatch):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    exe = bin_ / "aws"
    exe.write_text(FAKE.replace("{py}", sys.executable))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    st = tmp_path / "state.json"
    st.write_text(json.dumps(dict(versions=["$LATEST", "1"], aliases={"live": "1", "previous": "1"}, status="Successful", alarm="OK", invoke="200")))
    monkeypatch.setenv("PATH", f"{bin_}:" + __import__("os").environ["PATH"])
    monkeypatch.setenv("FAKE_STATE", str(st))
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.log"))
    monkeypatch.setenv("FAKE_ACCOUNT", "123456789012")
    prof = tmp_path / "aws.json"
    prof.write_text(json.dumps(PROFILE))
    rows = [[t, c, "Not covered: not checked in this release"] for t in ("Serverless", "Cloud application services") for c in RL.A.CHECKS[t]]
    rl["docs"]["STEP 3"] = plan(m=rl["marker"], target_rows=CROSS + rows)
    return dict(rl, state=st, log=tmp_path / "calls.log", profile=prof, prof=PROFILE, mon=monkeypatch)


def state(a):
    return json.loads(a["state"].read_text())


def staged(a):
    RL.run_step("request", [str(a["req"])])
    run("readiness")
    RL.run_step("plan", [], None, str(a["profile"]))
    run("provenance", str(a["repo"]))
    run("config", str(a["repo"]))
    (a["ws"] / "release/promotions.jsonl").write_text(json.dumps(dict(env="staging", artifact="dist/app.tar", version="1.4.2", ok=True, at="x")) + "\n")


def test_the_profile_is_checked_before_any_command_is_built():
    assert AWS.validate(PROFILE) == []
    for change, why in ((dict(service="ecs"), "service must be 'lambda'"), (dict(account_id="1234"), "12-digit"), (dict(region="mars"), "region must look like"),
                        (dict(function="orders api; rm -rf /"), "function must be"), (dict(alias="x", previous_alias="x"), "must be different"),
                        (dict(package="../../etc/passwd"), "package must be"), (dict(package="dist/app zip.zip"), "package must be"),
                        (dict(package=None), "package is needed"), (dict(alarm="a b"), "alarm must be"), (dict(smoke_payload="{bad"), "valid JSON"),
                        (dict(smoke_payload="{\"a\":\"it's\"}"), "single quote")):
        assert any(why in b for b in AWS.validate({**PROFILE, **change})), change
    with pytest.raises(ValueError, match="12-digit"):
        AWS.commands({**PROFILE, "account_id": "x"})
    assert AWS.validate([]) == ["the AWS profile must be a JSON object"]


def test_the_commands_check_the_account_first_name_the_region_and_use_no_backticks():
    c = AWS.commands(PROFILE, "1.4.2", "abcdef0123456789abcd")
    first = c["promotion"][0][1]
    assert first.startswith("test ") and '"123456789012"' in first and AWS.expected_account([first]) == "123456789012"
    every = [x for k in ("promotion", "rollback") for _, x in c[k]] + [h[1] for h in c["health"]]
    assert all("`" not in x and "|" not in x for x in every) and all("--region eu-west-1" in x or "--region" in x for x in every)
    assert [x for _, x in c["promotion"] if "update-function-code" in x][0].endswith("--zip-file fileb://dist/app.zip --region eu-west-1")
    assert "release 1.4.2 abcdef012345" in [x for _, x in c["promotion"] if "publish-version" in x][0]
    assert "--name previous" in c["rollback"][0][1] and "--name live" in c["rollback"][0][1]
    assert [h[0] for h in c["health"]] == ["alias points at the newest version", "last code update succeeded", "CloudWatch alarm is OK", "smoke invocation returns 200"]
    s3 = AWS.commands({**PROFILE, "package": dict(s3_bucket="my-builds", s3_key="orders/app.zip")})
    assert "--s3-bucket my-builds --s3-key orders/app.zip" in s3["promotion"][2][1]
    lean = AWS.commands({k: v for k, v in PROFILE.items() if k not in ("alarm", "smoke_payload")})
    assert len(lean["health"]) == 2 and AWS.expected_account([]) == ""


def test_the_version_description_cannot_carry_shell_text():
    c = AWS.commands(PROFILE, '1.0"; rm -rf / #', "abc$(whoami)")
    d = [x for _, x in c["promotion"] if "publish-version" in x][0]
    assert "rm -rf" in d and '"; ' not in d and "$(" not in d.split("--description")[1]


def test_the_generated_sections_replace_what_the_model_wrote_and_keep_the_rest():
    model = "## Status\nDraft.\n## Promotion commands\n| Step | Command | Purpose |\n|---|---|---|\n| 1 | `echo invented` | x |\n\n## Health checks\nold\n\n## Rollback\nold\n\n## Communications\nkeep me\n"
    out = AWS.replace_sections(model, AWS.render(PROFILE, "1.4.2", "abc"))
    assert "echo invented" not in out and "old" not in out and "keep me" in out and out.count("aws lambda update-alias") >= 3 and "## Status\nDraft." in out


def test_the_plan_step_uses_the_profile_and_the_resulting_plan_passes_its_own_checks(aws):
    staged(aws)
    t = text(aws, "release-plan.md")
    assert "echo one" not in t and "aws lambda update-function-code" in t and "aws sts get-caller-identity" in t and RL.check_plan(aws["briefs"], t, None) == ""
    assert (aws["briefs"] / "aws-profile.json").exists() and any("AWS Lambda" in p for p in aws["seen"])


def test_an_invalid_profile_stops_the_plan_before_the_model_is_asked(aws, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({**PROFILE, "account_id": "abc"}))
    RL.run_step("request", [str(aws["req"])])
    run("readiness")
    n = len(aws["seen"])
    with pytest.raises(SystemExit, match="12-digit"):
        RL.run_step("plan", [], None, str(bad))
    assert len(aws["seen"]) == n
    bad.write_text("nope")
    with pytest.raises(SystemExit, match="must be JSON"):
        RL.run_step("plan", [], None, str(bad))


def test_promotion_moves_the_live_alias_and_remembers_the_previous_version_for_rollback(aws):
    staged(aws)
    run("promote", str(aws["repo"]))
    s = state(aws)
    t = text(aws, "deployment-log.md")
    assert "**PROMOTED.**" in t and s["versions"] == ["$LATEST", "1", "2"] and s["aliases"] == {"live": "2", "previous": "1"} and t.count("PASS") == 7
    calls = aws["log"].read_text().splitlines()
    assert calls[0].startswith("sts get-caller-identity") and calls.index(next(c for c in calls if "update-function-code" in c)) < calls.index(next(c for c in calls if "publish-version" in c))


def test_a_rollback_puts_the_previous_version_back(aws):
    staged(aws)
    run("promote", str(aws["repo"]))
    assert state(aws)["aliases"]["live"] == "2"
    aws["state"].write_text(json.dumps({**state(aws), "status": "Failed"}))  # the new version is unhealthy
    run("monitor", str(aws["repo"]))
    run("rollback", True, str(aws["repo"]))
    assert state(aws)["aliases"] == {"live": "1", "previous": "1"}


def test_a_failing_alarm_or_a_failed_update_shows_up_in_monitoring(aws):
    staged(aws)
    run("promote", str(aws["repo"]))
    aws["state"].write_text(json.dumps({**state(aws), "alarm": "ALARM"}))
    run("monitor", str(aws["repo"]))
    assert "CloudWatch alarm is OK" in text(aws, "rollout-health.md") and "FAIL" in text(aws, "rollout-health.md")


def test_the_wrong_account_or_an_expired_session_refuses_the_promotion_and_nothing_is_deployed(aws):
    staged(aws)
    aws["mon"].setenv("FAKE_ACCOUNT", "999999999999")
    with pytest.raises(SystemExit, match="AWS account: this machine's AWS session is not account 123456789012"):
        run("promote", str(aws["repo"]))
    assert not any("update-function-code" in c for c in aws["log"].read_text().splitlines()) and state(aws)["aliases"]["live"] == "1"
    aws["mon"].setenv("FAKE_ACCOUNT", "")
    with pytest.raises(SystemExit, match="not logged in.*session has expired"):
        run("promote", str(aws["repo"]))


def test_a_missing_alias_stops_the_promotion_before_any_code_is_uploaded(aws):
    staged(aws)
    s = state(aws)
    del s["aliases"]["previous"]
    aws["state"].write_text(json.dumps(s))
    run("promote", str(aws["repo"]))
    t = text(aws, "deployment-log.md")
    assert "**FAILED.**" in t and "stopped at step 2 of 7" in t and not any("update-function-code" in c for c in aws["log"].read_text().splitlines())


def test_the_account_guard_comes_from_the_approved_plan_not_from_a_profile_file_edited_later(aws):
    staged(aws)
    (aws["briefs"] / "aws-profile.json").write_text(json.dumps({**PROFILE, "account_id": "999999999999"}))
    run("promote", str(aws["repo"]))  # the plan, approved with 123456789012, is what decides
    assert "**PROMOTED.**" in text(aws, "deployment-log.md")
