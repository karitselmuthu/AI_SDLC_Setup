"""Technology and deployment coverage: release targets are found from repository, artifact and environment evidence; unsupported targets are disclosed."""
import subprocess

import pytest

from release import adapters as A
from release import agent as RL
from test_release import CROSS, TABLE, plan, record, rl, siblings, staged, text, run  # noqa: F401  (rl is a fixture)


def repo_with(tmp_path, files, name="r"):
    repo = tmp_path / name
    for f, body in files.items():
        (repo / f).parent.mkdir(parents=True, exist_ok=True)
        (repo / f).write_text(body)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


def names(det):
    return [t["target"] for t in det["targets"]]


def test_containers_are_found_from_files_manifest_contents_and_an_image_reference(tmp_path):
    repo = repo_with(tmp_path, {"Dockerfile": "FROM x", "deploy/web.yaml": "apiVersion: apps/v1\nkind: Deployment\n"})
    d = A.detect(repo, "registry.example.com/team/app@sha256:" + "a" * 64, [])
    t = next(x for x in d["targets"] if x["target"] == "Containers and orchestration")
    assert t["checks"] == ["Image identity", "Registry provenance", "Configuration", "Readiness probes", "Rollout status", "Rollback behavior"]
    assert "Dockerfile" in t["evidence"] and "deploy/web.yaml (contents)" in t["evidence"] and any("image reference" in e for e in t["evidence"])


def test_cloud_application_services_come_from_platform_files_or_cli_commands(tmp_path):
    d = A.detect(repo_with(tmp_path, {"appspec.yml": "version: 0.0"}), "", ["aws ecs update-service --cluster c"])
    t = next(x for x in d["targets"] if x["target"] == "Cloud application services")
    assert "Region" in t["checks"] and "Identity permissions" in t["checks"] and "appspec.yml" in t["evidence"] and any("aws ecs" in e for e in t["evidence"])


def test_serverless_is_told_apart_from_infrastructure_as_code_by_the_template_contents(tmp_path):
    sam = A.detect(repo_with(tmp_path, {"template.yaml": "Transform: AWS::Serverless-2016-10-31\n", "serverless.yml": "service: x"}, "a"), "", [])
    assert "Serverless" in names(sam) and "Infrastructure as code" not in names(sam)
    assert next(x for x in sam["targets"] if x["target"] == "Serverless")["checks"][-1] == "Rollback limitations"
    cfn = A.detect(repo_with(tmp_path, {"template.yaml": "AWSTemplateFormatVersion: '2010-09-09'\n"}, "b"), "", [])
    assert "Infrastructure as code" in names(cfn) and "Serverless" not in names(cfn)


def test_virtual_machines_and_data_centers_from_config_management_images_and_packages(tmp_path):
    d = A.detect(repo_with(tmp_path, {"playbook-web.yml": "- hosts: all", "image.pkr.hcl": "source"}), "app-1.4.2.rpm", ["ansible-playbook -i prod playbook-web.yml"])
    t = next(x for x in d["targets"] if x["target"] == "Virtual machines and data centers")
    assert t["checks"][:2] == ["Image or package identity", "Host readiness"] and len(t["evidence"]) >= 3 and "Configuration drift" in t["checks"]


def test_web_and_mobile_applications_from_manifests_distribution_tools_and_package_types(tmp_path):
    d = A.detect(repo_with(tmp_path, {"android/app/src/main/AndroidManifest.xml": "<m/>", "fastlane/Fastfile": "lane"}), "build/app-release.aab", [])
    t = next(x for x in d["targets"] if x["target"] == "Web and mobile applications")
    assert "Staged rollout" in t["checks"] and "Signing or package identity" in t["checks"] and any(".aab" in e or "aab package" in e for e in t["evidence"])
    assert "Web and mobile applications" in names(A.detect(None, "", ["upload with fastlane to TestFlight"]))


def test_data_and_database_changes_from_migrations_and_commands_but_not_from_the_word_migrate(tmp_path):
    d = A.detect(repo_with(tmp_path, {"db/migrate/001_add.sql": "ALTER TABLE a"}), "", ["alembic upgrade head"])
    t = next(x for x in d["targets"] if x["target"] == "Data and database changes")
    assert t["checks"] == ["Backward compatibility", "Migration order", "Lock or downtime risk", "Recovery strategy", "Data validation gates"] and len(t["evidence"]) == 2
    assert "Data and database changes" not in names(A.detect(None, "", ["we will migrate our users to the new look and feel"]))


def test_infrastructure_as_code_from_terraform_pulumi_and_cdk(tmp_path):
    for f in ("main.tf", "cdk.json", "Pulumi.dev.yaml"):
        assert "Infrastructure as code" in names(A.detect(repo_with(tmp_path, {f: "x"}, f.replace(".", "")), "", []))
    assert A.CHECKS["Infrastructure as code"] == ["Plan or diff review", "Policy checks", "Target scope", "Dependency order", "Change impact"]


def test_cross_cutting_delivery_systems_always_apply_and_name_the_pipeline_when_there_is_one(tmp_path):
    bare = A.detect(repo_with(tmp_path, {"app.py": "x"}, "a"), "", [])
    assert names(bare) == ["Cross-cutting delivery systems"] and "always considered" in bare["targets"][0]["evidence"][0]
    ci = A.detect(repo_with(tmp_path, {".github/workflows/release.yml": "on: push"}, "b"), "", [])
    assert ci["targets"][0]["evidence"] == [".github/workflows/release.yml"]
    assert A.CHECKS["Cross-cutting delivery systems"] == ["Approval enforcement", "Immutable artifacts", "Credentials scope", "Audit record", "Workflow integrity"]


def test_a_plain_application_gets_no_deployment_target_it_has_no_evidence_for(tmp_path):
    d = A.detect(repo_with(tmp_path, {"app.py": "print(1)", "README.md": "a service that updates records"}), "dist/app.tar", ["Deploy with ./deploy.sh staging 1.4.2"])
    assert names(d) == ["Cross-cutting delivery systems"] and d["unsupported"] == []


def test_targets_with_no_adapter_are_disclosed_as_unsupported_and_never_assumed(tmp_path):
    d = A.detect(repo_with(tmp_path, {"nightly.jcl": "//JOB", "app.nomad": "job", "manifest.yml": "applications:\n- name: x\n"}), "", ["then cf push, and heroku release"])
    got = {u["what"] for u in d["unsupported"]}
    assert {"Mainframe (JCL, COBOL)", "HashiCorp Nomad", "Cloud Foundry", "Heroku"} <= got and all("specialist" in u["why"] for u in d["unsupported"])
    assert "do NOT plan how to deploy" in A.prompt_note(d)
    assert A.detect(repo_with(tmp_path, {"manifest.yml": "name: browser-extension\n"}, "x"), "", [])["unsupported"] == []  # a bare manifest.yml is not Cloud Foundry


def test_every_check_of_every_detected_target_needs_a_row(tmp_path):
    d = A.detect(repo_with(tmp_path, {"Dockerfile": "FROM x"}), "", [])
    assert len(A.required(d)) == 6 + 5 and ("Containers and orchestration", "Rollout status") in A.required(d)


def test_how_a_check_is_covered_must_point_at_a_real_plan_item_a_named_person_or_an_honest_gap():
    p = plan(m="m")
    ok = ["Promotion command 1", "Rollback step 1", "Health check errors", "Configuration reference DB_URL", "Manual: compare the digest by the release engineer", "Not covered: no tooling", "Not applicable: static site"]
    assert all(RL.cover_problem(c, p) == "" for c in ok)
    assert "no promotion command 9" in RL.cover_problem("Promotion command 9", p) and "no health check with that name" in RL.cover_problem("Health check latency", p)
    assert "name a Promotion command" in RL.cover_problem("It is handled by the platform", p) and RL.cover_problem("Manual: do it", p) != ""  # a manual step needs a person


def test_the_plan_is_sent_back_until_every_detected_check_says_how_it_is_covered(rl, tmp_path):
    (rl["repo"] / "Dockerfile").write_text("FROM x")
    RL.run_step("request", [str(rl["req"])], str(rl["repo"]))
    msg = RL.check_plan(rl["briefs"], plan(m="m"), None, "")  # only the cross-cutting rows
    assert "Containers and orchestration: Image identity" in msg and "Rollback behavior" in msg
    rows = CROSS + [["Containers and orchestration", c, "Promotion command 1"] for c in A.CHECKS["Containers and orchestration"]]
    assert RL.check_plan(rl["briefs"], plan(m="m", target_rows=rows), None, "") == ""
    bad = CROSS + [["Containers and orchestration", c, "the platform handles it" if c == "Rollout status" else "Promotion command 1"] for c in A.CHECKS["Containers and orchestration"]]
    assert "Rollout status (name a Promotion command" in RL.check_plan(rl["briefs"], plan(m="m", target_rows=bad), None, "")


def test_commands_in_the_plan_count_as_evidence_but_its_own_coverage_table_does_not(rl):
    RL.run_step("request", [str(rl["req"])])
    assert RL.check_plan(rl["briefs"], plan(m="m", target_rows=CROSS + [["Containers and orchestration", "Image identity", "Not covered: kubectl is not used"]]), None, "") == ""
    assert "Containers and orchestration: Image identity" in RL.check_plan(rl["briefs"], plan(m="m", promote=("kubectl apply -f k8s/",)), None, "")


def test_an_unsupported_target_must_be_named_in_the_plan_as_needing_a_specialist(rl):
    (rl["repo"] / "nightly.jcl").write_text("//JOB")
    RL.run_step("request", [str(rl["req"])], str(rl["repo"]))
    assert "Name the unsupported target(s)" in RL.check_plan(rl["briefs"], plan(m="m"), None, "") and "Mainframe" in RL.check_plan(rl["briefs"], plan(m="m"), None, "")
    rows = CROSS + [["Mainframe (JCL, COBOL)", "All checks", "Not covered: needs a mainframe specialist"]]
    assert RL.check_plan(rl["briefs"], plan(m="m", target_rows=rows), None, "") == ""


def test_the_plan_prompt_lists_the_detected_targets_and_their_exact_check_names(rl):
    (rl["repo"] / "main.tf").write_text("x")
    RL.run_step("request", [str(rl["req"])], str(rl["repo"]))
    RL.run_step("plan", [], None)
    prompt = next(p for p in rl["seen"] if "Deployment targets detected by code" in p)  # the first prompt; a repair prompt may follow it
    assert "Infrastructure as code: Plan or diff review; Policy checks; Target scope; Dependency order; Change impact" in prompt and "Cross-cutting delivery systems:" in prompt


def test_readiness_reports_detected_targets_and_unsupported_ones_before_and_after_there_is_a_plan(rl):
    (rl["repo"] / "Dockerfile").write_text("FROM x")
    (rl["repo"] / "nightly.jcl").write_text("//JOB")
    RL.run_step("request", [str(rl["req"])], str(rl["repo"]))
    RL.run_readiness(str(rl["repo"]))
    t = text(rl, "readiness.md")
    assert "## Deployment coverage" in t and "Containers and orchestration" in t and "Mainframe (JCL, COBOL)" in t and "Release checks" not in t  # no plan yet
    rows = CROSS + [["Containers and orchestration", c, "Not covered: x" if c == "Rollout status" else "Promotion command 1"] for c in A.CHECKS["Containers and orchestration"]]
    rl["docs"]["STEP 3"] = plan(m=rl["marker"], target_rows=rows + [["Mainframe (JCL, COBOL)", "All checks", "Not covered: specialist"]])
    RL.run_step("plan", [])
    RL.run_readiness()
    t = text(rl, "readiness.md")
    assert "| Containers and orchestration | Rollout status | Not covered |" in t and "| Containers and orchestration | Image identity | Addressed |" in t


def test_promotion_tells_the_release_manager_which_checks_the_plan_does_not_cover(rl, capsys):
    staged(rl)
    run("promote", str(rl["repo"]))
    out = capsys.readouterr().out
    assert "WARNING: 5 release check(s) are not covered by this plan" in out and "Cross-cutting delivery systems: Approval enforcement is not covered" in out


def test_the_release_history_records_the_deployment_coverage(rl):
    staged(rl)
    run("promote", str(rl["repo"]))
    run("monitor", str(rl["repo"]))
    run("rollback", False, str(rl["repo"]))
    run("close")
    t = text(rl, "release-history.md")
    assert "## Deployment coverage" in t and "| Cross-cutting delivery systems | Audit record | Not covered |" in t and "Unsupported targets" in t
