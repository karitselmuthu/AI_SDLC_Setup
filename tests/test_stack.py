"""The stack scanner (coder/stack.py): finds the files that define a project's stack. Plain code, no model."""
from coder import stack


def _repo(tmp_path, *paths):
    for p in paths:
        f = tmp_path / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x")
    return tmp_path


def test_finds_manifests_lockfiles_build_config_and_ci_including_nested_and_globbed_names(tmp_path):
    repo = _repo(tmp_path, "pyproject.toml", "requirements-dev.txt", "web/package.json", "web/yarn.lock",
                 "Dockerfile.prod", "Makefile", "web/tsconfig.base.json", ".python-version", "app/App.csproj",
                 ".github/workflows/ci.yml", ".github/workflows/notes.md", ".gitlab-ci.yml", "src/main.py")
    f = stack.scan(repo)["files"]
    assert f["manifest"] == ["app/App.csproj", "pyproject.toml", "requirements-dev.txt", "web/package.json"]
    assert f["lockfile"] == ["web/yarn.lock"]
    assert f["build"] == ["Dockerfile.prod", "Makefile"]
    assert f["framework config"] == [".python-version", "web/tsconfig.base.json"]
    assert f["ci"] == [".github/workflows/ci.yml", ".gitlab-ci.yml"]  # a .md in the workflows folder is not CI


def test_skips_vendored_and_generated_folders(tmp_path):
    repo = _repo(tmp_path, "package.json", "node_modules/dep/package.json", ".git/config", "venv/lib/setup.py",
                 "dist/app.js", "src/a.py")
    found = stack.scan(repo)
    assert found["files"] == {"manifest": ["package.json"]} and found["languages"] == {"Python": 1}


def test_counts_languages_and_reports_unrecognised_types_but_not_data_or_docs(tmp_path):
    repo = _repo(tmp_path, "a.py", "b.py", "c.ts", "legacy/PAY.cob", "legacy/ACCT.cob", "x.nat", "README.md",
                 "data.json", "logo.png", "notes.txt", "Makefile")
    found = stack.scan(repo)
    assert found["languages"] == {"Python": 2, "TypeScript": 1}  # most files first
    assert found["unrecognised"] == {".cob": 2, ".nat": 1}  # json, md, png, txt are data; Makefile has no extension


def test_a_huge_repo_is_reported_as_truncated_not_silently_cut(tmp_path, monkeypatch):
    repo = _repo(tmp_path, "a.py", "b.py", "c.py", "d.py")
    monkeypatch.setattr(stack, "MAX_FILES", 3)
    found = stack.scan(repo)
    assert found["truncated"] and "stopped after 3 files" in stack.render(found)


def test_render_lists_every_category_even_when_empty(tmp_path):
    out = stack.render(stack.scan(_repo(tmp_path, "pyproject.toml")))
    assert "manifest: pyproject.toml" in out and "lockfile: none found" in out and "ci: none found" in out
    assert "unrecognised file types (no known language): none" in out


def test_missing_reports_unmentioned_files_and_file_types(tmp_path):
    found = stack.scan(_repo(tmp_path, "pyproject.toml", "uv.lock", "x.cob"))
    assert stack.missing(found, "`pyproject.toml` and `.cob` files") == ["uv.lock"]
    assert stack.missing(found, "pyproject.toml uv.lock .cob") == []
