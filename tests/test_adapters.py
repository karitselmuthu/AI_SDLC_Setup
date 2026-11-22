"""Stack adapters (coder/adapters.py): detect what a repository really uses, select only that technology's checks, and report
what was not run and why. Repositories here are tiny fixtures in a temp dir; tool availability is faked so the tests do not
depend on what is installed on the machine."""
import json
import re

import pytest

from coder import adapters as a


@pytest.fixture(autouse=True)
def tools(monkeypatch):
    """Pretend these tools are installed (tests override per case). Probes pass unless a test says otherwise."""
    have = {"ruff", "mypy", "pytest", "npm", "yarn", "pnpm", "npx", "mvn", "gradle", "go", "cargo", "dotnet", "bundle", "helm",
            "terraform", "flutter", "dart", "swift", "cfn-lint", "kubeconform", "composer", "python3", "buf", "spectral"}
    monkeypatch.setattr(a.shutil, "which", lambda t: f"/bin/{t}" if t in have else None)
    monkeypatch.setattr(a, "_probe_ok", lambda repo, probe: True)
    return have


def mk(tmp_path, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def stacks(p):
    return {s["name"]: s for s in p["stacks"]}


def checks(p, cat=None):
    return {c["cmd"]: c for c in p["checks"] if cat in (None, c["cat"])}


def gap_kinds(p, stack_prefix):
    return {g["cat"] for g in p["gaps"] if g["stack"].startswith(stack_prefix)}


def test_an_empty_repository_has_no_stack_and_nothing_is_invented(tmp_path):
    p = a.plan(mk(tmp_path, {"README.md": "hi"}))
    assert p["stacks"] == p["checks"] == p["gaps"] == p["unsupported"] == []
    assert "No supported stack was detected" in a.prompt_note(p) and a.render(p) == "stack adapters: no supported technology detected"


def test_python_is_detected_from_its_files_and_only_configured_checks_are_selected(tmp_path):
    p = a.plan(mk(tmp_path, {"pyproject.toml": "[tool.ruff]\nline-length=100\n[tool.mypy]\nstrict=true\n", "app.py": "x=1\n",
                             "tests/test_app.py": "def test_x(): pass\n", "uv.lock": ""}))
    s = stacks(p)["Python"]
    assert s["area"] == "Backend services" and "pyproject.toml" in s["evidence"] and "pyproject.toml" in s["conventions"]
    got = checks(p)
    assert {"ruff format --check .", "ruff check .", "mypy .", "pytest -q"} <= set(got)
    assert "black --check ." not in got and "flake8" not in got and "pylint ." not in got  # no config, so not selected
    assert got["uv lock --check --offline"]["status"] == "not runnable" and "`uv` is not installed here" in got["uv lock --check --offline"]["reason"]


def test_a_data_or_ai_python_project_is_filed_under_data_engineering_and_gets_its_own_expectations(tmp_path):
    p = a.plan(mk(tmp_path, {"requirements.txt": "pandas\napache-airflow\n", "dags/etl.py": "x=1\n", "pytest.ini": ""}))
    assert stacks(p)["Python"]["area"] == "Data engineering and AI"
    assert gap_kinds(p, "Python") == {"schema", "deps"}  # tests exist; nothing can validate schemas offline; no lockfile


def test_a_missing_tool_is_reported_as_not_run_with_the_reason_not_dropped(tmp_path, tools):
    tools.discard("ruff")
    p = a.plan(mk(tmp_path, {"ruff.toml": "", "app.py": "x=1\n"}))
    c = checks(p)["ruff check ."]
    assert c["status"] == "not runnable" and c["reason"] == "`ruff` is not installed here"
    assert "ruff check ." not in a.runnable(p)


def test_node_uses_the_repositorys_own_scripts_and_package_manager_and_never_installs(tmp_path):
    pkg = {"scripts": {"lint": "eslint .", "test": "jest", "build": "tsc -b", "typecheck": "tsc --noEmit", "format:check": "prettier --check ."},
           "dependencies": {"react": "^18", "next": "14"}, "devDependencies": {"eslint": "9", "jest": "29"}}
    p = a.plan(mk(tmp_path, {"package.json": json.dumps(pkg), "pnpm-lock.yaml": "", "src/App.tsx": "export {}\n"}))
    s = stacks(p)
    name = next(n for n in s if n.startswith("JavaScript/TypeScript"))
    assert "React" in name and "Next.js" in name and s[name]["area"] == "Web frontend"
    assert {"package.json", "pnpm-lock.yaml", "package.json lists react"} <= set(s[name]["evidence"])
    got = checks(p)
    assert {"pnpm run lint", "pnpm test", "pnpm run build", "pnpm run typecheck", "pnpm run format:check"} <= set(got)
    assert all(c["status"] == "not runnable" and "never installs" in c["reason"] for c in got.values())  # no node_modules
    (tmp_path / "node_modules").mkdir()
    assert "pnpm test" in a.runnable(a.plan(tmp_path))


def test_the_default_npm_test_stub_is_not_a_check_and_missing_scripts_become_gaps(tmp_path):
    pkg = {"scripts": {"test": 'echo "Error: no test specified" && exit 1'}, "dependencies": {"express": "4"}}
    p = a.plan(mk(tmp_path, {"package.json": json.dumps(pkg), "package-lock.json": "{}"}))
    name = next(iter(stacks(p)))
    assert "Express" in name and stacks(p)[name]["area"] == "Backend services"
    assert "npm test" not in checks(p)
    assert {"test", "lint", "format", "build"} <= gap_kinds(p, "JavaScript")


def test_typescript_and_eslint_configs_select_direct_tools_when_there_are_no_scripts(tmp_path):
    pkg = {"devDependencies": {"typescript": "5", "eslint": "9"}}
    p = a.plan(mk(tmp_path, {"package.json": json.dumps(pkg), "tsconfig.json": "{}", "eslint.config.js": "", "package-lock.json": "{}"}))
    assert {"npx --no-install tsc --noEmit", "npx --no-install eslint ."} <= set(checks(p))


def test_react_native_and_electron_are_mobile_and_desktop(tmp_path):
    p = a.plan(mk(tmp_path, {"package.json": json.dumps({"dependencies": {"react-native": "0.7", "react": "18"}})}))
    assert next(iter(stacks(p).values()))["area"] == "Mobile and desktop"
    p = a.plan(mk(tmp_path / "e", {"package.json": json.dumps({"dependencies": {"electron": "30"}})}))
    assert next(iter(stacks(p).values()))["area"] == "Mobile and desktop"


def test_jvm_builds_run_offline_and_an_unresolvable_dependency_set_is_not_run(tmp_path, monkeypatch):
    mk(tmp_path, {"pom.xml": "<project><parent>spring-boot-starter-parent</parent><plugin>spotless</plugin></project>", "mvnw": "#!/bin/sh\n",
                  "src/main/java/A.java": "class A {}\n"})
    (tmp_path / "mvnw").chmod(0o755)
    p = a.plan(tmp_path)
    assert "Java/Kotlin (Maven, Spring Boot)" in stacks(p)
    got = checks(p)
    assert {"./mvnw -o -B -q test", "./mvnw -o -B -q test-compile", "./mvnw -o -B -q spotless:check"} <= set(got)
    assert all(re.search(r"\s-o\s", c) for c in got)  # offline
    monkeypatch.setattr(a, "_tool_ok", lambda repo, tool: True)
    monkeypatch.setattr(a, "_probe_ok", lambda repo, probe: False)
    p = a.plan(tmp_path)
    assert all(c["status"] == "not runnable" and "not available offline" in c["reason"] for c in p["checks"] if c["cmd"])


def test_android_gradle_gets_lint_and_a_manual_permission_review(tmp_path):
    p = a.plan(mk(tmp_path, {"build.gradle": "plugins { id 'com.android.application' }", "app/src/main/AndroidManifest.xml": "<manifest/>",
                             "app/src/main/java/A.kt": "class A\n"}))
    assert "Java/Kotlin (Gradle, Android)" in stacks(p) and stacks(p)["Java/Kotlin (Gradle, Android)"]["area"] == "Mobile and desktop"
    got = checks(p)
    assert {"gradle --offline assemble", "gradle --offline test", "gradle --offline lintDebug"} <= set(got)
    review = [c for c in p["checks"] if c["cat"] == "review"][0]
    assert review["status"] == "manual" and "AndroidManifest.xml" in review["reason"]


def test_dotnet_needs_restored_packages_and_is_never_restored_by_the_agent(tmp_path):
    p = a.plan(mk(tmp_path, {"App.csproj": "<Project/>", "Program.cs": "class P{}\n"}))
    got = checks(p)
    assert {"dotnet build --no-restore", "dotnet test --no-restore"} <= set(got)
    assert all("never restores" in c["reason"] for c in got.values() if c["status"] == "not runnable")
    mk(tmp_path, {"obj/project.assets.json": "{}"})
    assert "dotnet test --no-restore" in a.runnable(a.plan(tmp_path))


def test_go_rust_php_and_ruby_adapters_select_their_own_commands(tmp_path):
    p = a.plan(mk(tmp_path / "go", {"go.mod": "module x\n", "go.sum": "", "main.go": "package main\n"}))
    assert {"go build ./...", "go vet ./...", "go test ./...", "go mod verify"} <= set(checks(p))
    p = a.plan(mk(tmp_path / "rs", {"Cargo.toml": "[package]\n", "Cargo.lock": "", "src/main.rs": "fn main(){}\n"}))
    assert {"cargo fmt --check", "cargo clippy --offline", "cargo test --offline", "cargo build --offline"} <= set(checks(p))
    p = a.plan(mk(tmp_path / "php", {"composer.json": "{}", "phpunit.xml": "", "src/A.php": "<?php\n"}))
    phpunit = checks(p)["vendor/bin/phpunit"]
    assert phpunit["status"] == "not runnable" and "vendor/bin/phpunit" in phpunit["reason"]  # composer install was never run
    p = a.plan(mk(tmp_path / "rb", {"Gemfile": "", ".rubocop.yml": "", "spec/a_spec.rb": "", "a.rb": "x=1\n"}))
    assert {"bundle exec rubocop", "bundle exec rspec"} <= set(checks(p))


def test_flutter_and_swift_report_what_a_person_must_review(tmp_path):
    p = a.plan(mk(tmp_path / "fl", {"pubspec.yaml": "dependencies:\n  flutter:\n    sdk: flutter\n", "lib/main.dart": "void main(){}\n",
                                    "android/app/src/main/AndroidManifest.xml": "<manifest/>"}))
    assert stacks(p)["Dart/Flutter"]["area"] == "Mobile and desktop"
    assert {"flutter analyze --no-pub", "flutter test --no-pub"} <= set(checks(p))
    assert any(c["cat"] == "review" and "AndroidManifest.xml" in c["reason"] for c in p["checks"])
    p = a.plan(mk(tmp_path / "sw", {"App.xcodeproj/project.pbxproj": "", "App/A.swift": "import UIKit\n"}))
    assert any(c["status"] == "manual" and "scheme and a simulator" in c["reason"] for c in p["checks"])
    assert "swift test" not in checks(p)  # no Package.swift: the agent does not guess a scheme


def test_sql_migrations_and_datastores_are_reported_as_needing_a_database_not_checked(tmp_path):
    p = a.plan(mk(tmp_path, {"db/migrations/001.sql": "create table t(id int);\n", "docker-compose.yml": "services:\n  db:\n    image: postgres:16\n  c:\n    image: redis\n"}))
    assert "SQL" in stacks(p) and next(n for n in stacks(p) if n.startswith("Datastores")) == "Datastores (PostgreSQL, Redis)"
    manual = [c for c in p["checks"] if c["status"] == "manual"]
    assert any("needs a database or warehouse" in c["reason"] for c in manual) and any("running database" in c["reason"] for c in manual)
    assert not any(c["cat"] == "schema" and c["status"] == "runnable" for c in p["checks"])


def test_infrastructure_checks_are_validation_only_and_apply_is_never_offered(tmp_path):
    p = a.plan(mk(tmp_path, {"main.tf": 'resource "x" "y" {}\n', "charts/app/Chart.yaml": "name: app\n", "cdk.json": "{}", "Pulumi.yaml": "name: p\n",
                             "cfn/t.yaml": "AWSTemplateFormatVersion: '2010-09-09'\nResources: {}\n",
                             "k8s/d.yaml": "apiVersion: apps/v1\nkind: Deployment\nmetadata: {}\n"}))
    s = stacks(p)
    assert {"Terraform", "Helm", "AWS CDK", "Pulumi", "CloudFormation", "Kubernetes manifests"} <= set(s)
    got = checks(p)
    assert got["terraform fmt -check -recursive"]["status"] == "runnable"
    assert got["terraform validate"]["status"] == "not runnable" and "never initialises" in got["terraform validate"]["reason"]
    assert {"helm lint charts/app", "helm template charts/app", "cfn-lint cfn/t.yaml"} <= set(got)
    assert any(c["stack"] == "AWS CDK" and c["status"] == "manual" and "synth" in c["reason"] for c in p["checks"])
    assert any(c["stack"] == "Pulumi" and c["status"] == "manual" for c in p["checks"])
    assert not any(re.search(r"\b(apply|destroy|deploy|up)\b", c["cmd"] or "") for c in p["checks"])
    assert "policy" in gap_kinds(p, "Terraform")


def test_interfaces_are_detected_and_without_contract_tooling_it_says_so(tmp_path):
    p = a.plan(mk(tmp_path, {"api/openapi.yaml": "openapi: 3.0.0\n", "proto/a.proto": 'syntax = "proto3";\n', "schema.graphql": "type Q { a: Int }\n"}))
    s = stacks(p)["Interfaces and shared schemas"]
    assert s["area"] == "Cross-stack interfaces" and "api/openapi.yaml" in s["evidence"]
    assert "spectral lint api/openapi.yaml" not in checks(p) and "buf lint" not in checks(p)  # no tool configured, so none is chosen
    assert not p["unsupported"]  # .proto and .graphql belong to this adapter, they are not "unrecognised"
    p = a.plan(mk(tmp_path, {".spectral.yaml": "", "buf.yaml": ""}))
    assert {"spectral lint api/openapi.yaml", "buf lint"} <= set(checks(p))
    assert any(c["status"] == "manual" and "no automated compatibility check" in c["reason"] for c in p["checks"])


def test_unsupported_languages_and_file_types_are_reported_not_guessed(tmp_path):
    p = a.plan(mk(tmp_path, {"lib/a.ex": "defmodule A do end\n", "x.cpp": "int main(){}\n", "q.weird": "?", "Main.java": "class Main {}\n"}))
    what = " | ".join(f"{u['what']}: {u['reason']}" for u in p["unsupported"])
    assert "Elixir (1 files): no adapter for this language" in what and "C++ (1 files): no adapter" in what
    assert ".weird files (1): unrecognised file type" in what
    assert "Java (1 files): source files found but no Java manifest or build file" in what
    assert p["stacks"] == [] and p["checks"] == []  # nothing was selected for any of it
    assert "No adapter exists for" in a.prompt_note(a.plan(tmp_path)) or "No supported stack" in a.prompt_note(p)


def test_every_command_an_adapter_can_select_is_check_mode_and_never_installs_or_deploys(tmp_path):
    mk(tmp_path, {"pyproject.toml": "[tool.ruff]\n[tool.mypy]\n[tool.black]\n[tool.pylint]\n[tool.pyright]\n", "manage.py": "", "poetry.lock": "", "uv.lock": "",
                  "package.json": json.dumps({"scripts": {"lint": "x", "test": "y", "build": "z", "format:check": "f", "typecheck": "t"}, "dependencies": {"react": "1"}}),
                  "yarn.lock": "", "pom.xml": "<p>spotless checkstyle</p>", "build.gradle": "spotless ktlint detekt checkstyle com.android", "App.csproj": "", ".editorconfig": "",
                  "go.mod": "", "go.sum": "", ".golangci.yml": "", "Cargo.toml": "", "Cargo.lock": "", "composer.json": "", "composer.lock": "", "phpunit.xml": "",
                  "phpstan.neon": "", ".php-cs-fixer.php": "", "Gemfile": "", "Gemfile.lock": "", ".rubocop.yml": "", ".rspec": "", "Package.swift": "", ".swiftlint.yml": "",
                  "pubspec.yaml": "flutter", "a.sql": "", ".sqlfluff": "", "main.tf": "", ".tflint.hcl": "", ".checkov.yml": "", "Chart.yaml": "", "openapi.yaml": "", "buf.yaml": "",
                  ".spectral.yaml": "", "t.yaml": "AWSTemplateFormatVersion: x\n", "rules/a.guard": ""})
    never = re.compile(r"(?<![\w-])(install|ci|add|deploy|apply|destroy|publish|push|rm|sudo|curl|wget|docker|kubectl|git|--fix|-w)(?![\w-])|[;&|><`$]")
    cmds = [c["cmd"] for c in a.plan(tmp_path)["checks"] if c["cmd"]]
    assert len(cmds) > 40
    for c in cmds:
        assert not never.search(c), c
    assert "ruff format --check ." in cmds and "black --check ." in cmds and "cargo fmt --check" in cmds  # formatters only check


def test_coverage_never_reports_a_pass_for_a_check_that_did_not_run(tmp_path):
    p = a.plan(mk(tmp_path, {"package.json": json.dumps({"scripts": {"test": "jest", "lint": "eslint ."}}), "package-lock.json": "{}", "main.tf": "x"}))
    res = [{"cmd": "terraform fmt -check -recursive", "rc": 0}]
    text = a.coverage(p, a.runnable(p), True, res)
    assert re.search(r"`terraform fmt -check -recursive` \| PASS \(exit 0\)", text)
    assert re.search(r"`npm test` \| Not run: dependencies are not installed", text) and "PASS" not in re.findall(r"`npm test`[^\n]*", text)[0]
    assert "Checks selected (" in text and "), run (1)," in text
    text = a.coverage(p, a.runnable(p), False, [], approved=False)  # the human did not approve the list
    assert "PASS" not in text.replace("only PASS or FAIL", "") and "Not run: the list was not approved" in text
    assert a.summary(p, a.runnable(p), False, [], approved=False).startswith(" Coverage is not complete:")


def test_a_failing_check_is_reported_as_fail_and_a_given_check_overrides_the_selection(tmp_path):
    p = a.plan(mk(tmp_path, {"main.tf": "x"}))
    assert "FAIL (exit 3)" in a.coverage(p, a.runnable(p), True, [{"cmd": "terraform fmt -check -recursive", "rc": 3}])
    text = a.coverage(p, ["make mine"], True, [{"cmd": "make mine", "rc": 0}], overridden=True)
    assert "Not run: replaced by the --check commands given" in text and re.search(r"`make mine` \| PASS \(exit 0\)", text)


def test_gaps_name_the_kind_of_check_and_the_reason_for_each_stack(tmp_path):
    p = a.plan(mk(tmp_path, {"Cargo.toml": "", "src/main.rs": "fn main(){}\n"}))
    assert gap_kinds(p, "Rust") == {"deps"}  # fmt, lint, build, test all exist; but there is no Cargo.lock
    assert [g["reason"] for g in p["gaps"]] == ["no lockfile was found, so lockfile consistency cannot be checked"]
    p = a.plan(mk(tmp_path / "t", {"main.tf": "x"}))
    reasons = {g["cat"]: g["reason"] for g in p["gaps"]}
    assert reasons["policy"] == "no policy check is configured or detectable for this stack"


def test_render_and_prompt_note_carry_the_evidence_and_the_unsupported_list(tmp_path):
    p = a.plan(mk(tmp_path, {"pytest.ini": "", "a.py": "x=1\n", "b.lua": "print(1)\n"}))
    r = a.render(p)
    assert "Python [Backend services]" in r and "Lua (1 files): no adapter" in r
    note = a.prompt_note(p)
    assert "pytest.ini" in note and "No adapter exists for: Lua (1 files)" in note and "instead of guessing" in note
