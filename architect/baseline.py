"""Approval ledger and versioned solution baseline (step 11). Plain code, no model calls.

briefs/approvals.log   one JSON line per human approval: step, file, sha256, reviewer, n (log position)
baseline/vN/           an immutable copy of every approved artifact + manifest.json (hashes, approvers, sources)
"""
import hashlib
import json
import os
import pathlib
import shutil
from datetime import datetime, timezone


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def log_approval(briefs, step, path, reviewer):
    """Record that a human approved this exact file content (the hash pins the content)."""
    path = pathlib.Path(path)
    with (pathlib.Path(briefs) / "approvals.log").open("a") as f:
        f.write(json.dumps(dict(step=step, file=path.name, sha256=sha256(path), reviewer=reviewer)) + "\n")


def log_skip(briefs, step, path, person, reason):
    """A person decided this step is not needed. The code wrote a placeholder document; this entry pins it. It satisfies every reviewer role
    of the step (nobody approved content, a person approved leaving the step out), and the report names who and why."""
    path = pathlib.Path(path)
    with (pathlib.Path(briefs) / "approvals.log").open("a") as f:
        f.write(json.dumps(dict(step=step, file=path.name, sha256=sha256(path), reviewer=f"SKIPPED by {person}", skipped=True, reason=reason)) + "\n")


def skipped(briefs, file):
    """The skip record for this file if its current content is exactly the placeholder a person approved skipping, else None."""
    rec, path = latest(briefs).get(file), pathlib.Path(briefs) / file
    return rec if rec and rec.get("skipped") and path.exists() and sha256(path) == rec["sha256"] else None


def latest(briefs):
    """file -> its most recent approval record, with n = position in the log (later approval = larger n)."""
    log = pathlib.Path(briefs) / "approvals.log"
    recs = {}
    for n, line in enumerate(log.read_text().splitlines() if log.exists() else []):
        if line.strip():
            rec = json.loads(line)
            recs[rec["file"]] = {**rec, "n": n}
    return recs


def signed_roles(briefs, file, sha):
    """Reviewers (in the order they signed) who approved exactly this content of this file."""
    log = pathlib.Path(briefs) / "approvals.log"
    recs = [json.loads(line) for line in log.read_text().splitlines() if line.strip()] if log.exists() else []
    return list(dict.fromkeys(r["reviewer"] for r in recs if r["file"] == file and r["sha256"] == sha))


def problems(briefs, steps):
    """Why these artifacts cannot be baselined yet. steps: {name: (template, file, reviewer, prior files)}.
    reviewer is one role (str) or several (list): every listed role must have approved the current content."""
    ap, out = latest(briefs), []
    for step, (_, file, reviewer, prior) in steps.items():
        path = pathlib.Path(briefs) / file
        if not path.exists():
            out.append(f"{file}: not produced (run `{step}`)")
        elif file not in ap:
            out.append(f"{file}: not approved (run `{step}` and approve it)")
        else:
            if sha256(path) != ap[file]["sha256"]:
                out.append(f"{file}: edited after it was approved (re-run `{step}`)")
            elif ap[file].get("skipped"):
                pass  # a person approved leaving this step out; only the staleness check below applies
            elif not isinstance(reviewer, str):
                signed = signed_roles(briefs, file, ap[file]["sha256"])
                out += [f"{file}: awaiting sign-off from {r} (run `{step}`)" for r in reviewer if r not in signed]
            out += [f"{file}: stale, {p} was re-approved after it (re-run `{step}`)"
                    for p in prior if p in ap and ap[p]["n"] > ap[file]["n"]]
    return out


def next_version(base):
    nums = [int(d.name[1:]) for d in pathlib.Path(base).glob("v*") if d.name[1:].isdigit()]
    return max(nums, default=0) + 1


def previous_doc(base, version, handoff_file):
    p = pathlib.Path(base) / f"v{version - 1}" / handoff_file
    return p if p.exists() else None


def package(briefs, base, steps, handoff_file, version, sources):
    """Copy the approved artifacts and the handoff document into baseline/v<version>/ with a manifest; read-only."""
    briefs, dest, ap = pathlib.Path(briefs), pathlib.Path(base) / f"v{version}", latest(briefs)
    dest.mkdir(parents=True)  # raises if the version already exists: versions are never overwritten
    files = [(step, file) for step, (_, file, _, _) in steps.items()] + [("handoff", handoff_file)]
    for _, file in files:
        shutil.copy2(briefs / file, dest / file)
    manifest = dict(
        version=version, previous_version=version - 1 or None,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        status="approved",  # a baseline directory exists only after every required reviewer signed
        artifacts=[dict(step=s, file=f, sha256=ap[f]["sha256"],
                        approved_by=ap[f]["reviewer"] + ": " + ap[f].get("reason", "") if ap[f].get("skipped") else ", ".join(signed_roles(briefs, f, ap[f]["sha256"]))) for s, f in files],
        source_documents=[dict(path=str(p), sha256=sha256(p)) for p in map(pathlib.Path, sources) if p.is_file()],
    )
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2))
    for f in dest.iterdir():
        os.chmod(f, 0o444)
    return dest
