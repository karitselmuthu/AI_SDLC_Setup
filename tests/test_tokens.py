"""Token measurement: core.ask records the CLI's real usage per call and still returns only the text."""
import json
import subprocess
import sys

import core

FAKE = json.dumps(dict(result="## Status\nhi", total_cost_usd=0.0123, num_turns=1,
                       usage=dict(input_tokens=5, cache_creation_input_tokens=6000, cache_read_input_tokens=100, output_tokens=40)))


def run(monkeypatch, tmp_path, stdout):
    monkeypatch.setenv("SDLC_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(core, "sessions", {})
    core.AGENTS["t"] = dict(role="r", tools=core.RO)
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: (seen.append(cmd), type("R", (), dict(stdout=stdout))())[1])
    monkeypatch.setattr(sys, "argv", ["/x/qa/agent.py", "scope"])
    return core.ask("t", "p"), seen[0]


def test_ask_returns_the_text_uses_lean_flags_and_logs_real_usage(monkeypatch, tmp_path):
    text, cmd = run(monkeypatch, tmp_path, FAKE)
    assert text == "## Status\nhi"
    assert all(f in cmd for f in ("--disable-slash-commands", "--strict-mcp-config", "--output-format")) and cmd[cmd.index("--setting-sources") + 1] == ""
    row = json.loads((tmp_path / "usage.jsonl").read_text())
    assert (row["step"], row["input"], row["cache_write"], row["cache_read"], row["output"], row["usd"]) == ("qa:scope", 5, 6000, 100, 40, 0.0123)


def test_a_non_json_reply_is_returned_unchanged_and_nothing_is_logged(monkeypatch, tmp_path):
    text, _ = run(monkeypatch, tmp_path, "Error: usage limit reached")
    assert text == "Error: usage limit reached" and not (tmp_path / "usage.jsonl").exists()


def test_the_report_adds_up_by_step(tmp_path):
    rows = [dict(step="qa:scope", agent="qa", input=2, cache_write=100, cache_read=0, output=10, usd=0.1, secs=5),
            dict(step="qa:scope", agent="qa", input=3, cache_write=0, cache_read=100, output=20, usd=0.05, secs=4)]
    (tmp_path / "usage.jsonl").write_text("\n".join(map(json.dumps, rows)))
    out = subprocess.run([sys.executable, str(core.pathlib.Path(core.__file__).parent / "tokens.py"), str(tmp_path)], capture_output=True, text=True).stdout
    assert "qa:scope" in out and "all input-side tokens: 205; output tokens: 30" in out and "0.15" in out
