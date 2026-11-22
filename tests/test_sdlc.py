import sdlc


def test_retry_until_green(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(sdlc, "ask", lambda a, p: calls.append(p) or "")
    # fails first run, passes once the "fix" marker exists
    cmd = "test -f ok || (touch ok; exit 1)"
    assert sdlc.test_loop(cmd) is True and len(calls) == 1


def test_review_fix_commits_on_new_branch(tmp_path, monkeypatch):
    import subprocess
    sh = lambda c: subprocess.run(c, shell=True, cwd=tmp_path, capture_output=True, text=True).stdout.strip()
    sh("git init -q && git commit -q --allow-empty -m init")
    replies = iter(["bug in x.py:1", "NO ISSUES"])

    def fake(agent, p):
        if agent == "coding":
            (tmp_path / "x.py").write_text("fixed")
            return ""
        return next(replies)

    monkeypatch.setattr(sdlc, "ask", fake)
    monkeypatch.setattr(sdlc, "approve", lambda who: True)
    sdlc.review_fix(str(tmp_path))
    assert sh("git branch --show-current").startswith("sdlc-fixes-")
    assert "review fixes round 1" in sh("git log --oneline") and not sh("git status --porcelain")


def test_refuses_dirty_repo(tmp_path):
    import subprocess, pytest
    subprocess.run("git init -q && touch f", shell=True, cwd=tmp_path)
    with pytest.raises(SystemExit):
        sdlc.review_fix(str(tmp_path))


def test_gives_up(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sdlc, "ask", lambda a, p: "")
    assert sdlc.test_loop("false", max_tries=2) is False
