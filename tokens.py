#!/usr/bin/env python3
"""Token and cost report from usage.jsonl (written by core.ask for every model call).
  python tokens.py [WORKSPACE_DIR]      default: this folder.   Shows each agent step: calls, input, cache, output tokens, cost, time."""
import json
import pathlib
import sys
from collections import defaultdict

ws = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent
log = ws / "usage.jsonl"
rows = [json.loads(l) for l in log.read_text().splitlines() if l.strip()] if log.exists() else []
if not rows:
    sys.exit(f"No model calls recorded in {log} yet.")
by = defaultdict(lambda: dict(calls=0, input=0, cache_write=0, cache_read=0, output=0, usd=0.0, secs=0.0))
for r in rows:
    for k in by[r["step"] or r["agent"]]:
        by[r["step"] or r["agent"]][k] += r.get(k, 0) if k != "calls" else 1
print(f"{'step':<22}{'calls':>6}{'input':>9}{'cache wr':>10}{'cache rd':>10}{'output':>9}{'USD':>8}{'secs':>7}")
tot = defaultdict(float)
for step, v in by.items():
    print(f"{step:<22}{v['calls']:>6}{v['input']:>9}{v['cache_write']:>10}{v['cache_read']:>10}{v['output']:>9}{v['usd']:>8.2f}{v['secs']:>7.0f}")
    for k, x in v.items():
        tot[k] += x
print(f"{'TOTAL':<22}{int(tot['calls']):>6}{int(tot['input']):>9}{int(tot['cache_write']):>10}{int(tot['cache_read']):>10}{int(tot['output']):>9}{tot['usd']:>8.2f}{tot['secs']:>7.0f}")
print(f"all input-side tokens: {int(tot['input'] + tot['cache_write'] + tot['cache_read'])}; output tokens: {int(tot['output'])}")
