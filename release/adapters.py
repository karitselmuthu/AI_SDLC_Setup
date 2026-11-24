"""Release adapters: which kinds of deployment a release involves, found from repository, artifact and environment evidence, and which release checks matter for each.
Plain code, no model. The agent has no native integration with any platform: it knows what to check, verifies the plan says how each check is covered, and runs only the
commands the Release Manager approved. A technology with no adapter is disclosed as unsupported, never assumed to be deployable.
detect(repo, artifact, texts) -> dict(targets=[dict(target, checks, evidence)], unsupported=[dict(what, why)])   required(det)   render(det)   prompt_note(det)
"""
import pathlib
import re
import subprocess

CHECKS = {
    "Containers and orchestration": ["Image identity", "Registry provenance", "Configuration", "Readiness probes", "Rollout status", "Rollback behavior"],
    "Cloud application services": ["Target account or project", "Region", "Identity permissions", "Environment configuration", "Health status", "Promotion path"],
    "Serverless": ["Package version", "Triggers", "Permissions", "Concurrency settings", "Compatibility", "Rollback limitations"],
    "Virtual machines and data centers": ["Image or package identity", "Host readiness", "Configuration drift", "Deployment order", "Recovery process"],
    "Web and mobile applications": ["Environment", "Release channel", "Signing or package identity", "Staged rollout", "User-impact checks"],
    "Data and database changes": ["Backward compatibility", "Migration order", "Lock or downtime risk", "Recovery strategy", "Data validation gates"],
    "Infrastructure as code": ["Plan or diff review", "Policy checks", "Target scope", "Dependency order", "Change impact"],
    "Cross-cutting delivery systems": ["Approval enforcement", "Immutable artifacts", "Credentials scope", "Audit record", "Workflow integrity"],
}
# file names (paths in the repository), file contents (first 4 KB of a few yaml/json files) and command or prose mentions (request, plan)
FILES = {
    "Containers and orchestration": r"(?i)(^|/)(dockerfile[^/]*|containerfile|docker-compose[^/]*\.ya?ml|chart\.ya?ml|kustomization\.ya?ml|skaffold\.ya?ml|task-definition[^/]*\.json)$|(^|/)(helm|charts|k8s|kubernetes)/",
    "Cloud application services": r"(?i)(^|/)(appspec\.ya?ml|app\.yaml|buildspec\.ya?ml|cloudbuild\.ya?ml|\.ebextensions/|\.platform/)",
    "Serverless": r"(?i)(^|/)(serverless\.(ya?ml|ts|js)|samconfig\.toml|host\.json|function\.json)$|(^|/)netlify/functions/",
    "Virtual machines and data centers": r"(?i)\.pkr\.hcl$|(^|/)(playbook[^/]*\.ya?ml|ansible\.cfg|berksfile|puppetfile)$|(^|/)(cookbooks|roles)/|\.(ova|vmdk|ami)$",
    "Web and mobile applications": r"(?i)(^|/)(androidmanifest\.xml|info\.plist|fastfile|netlify\.toml|vercel\.json|firebase\.json|pubspec\.yaml)$|\.(xcodeproj|apk|aab|ipa)$",
    "Data and database changes": r"(?i)\.sql$|(^|/)(migrations?|alembic|db/migrate|flyway|liquibase|dags)/|schema\.prisma$|dbt_project\.ya?ml$",
    "Infrastructure as code": r"(?i)\.(tf|tfvars)$|(^|/)(cdk\.json|pulumi(\.[\w-]+)?\.ya?ml)$",
    "Cross-cutting delivery systems": r"(?i)(^|/)(\.github/workflows/|\.gitlab-ci\.ya?ml|jenkinsfile|azure-pipelines\.ya?ml|\.circleci/|bitbucket-pipelines\.ya?ml|\.drone\.ya?ml)",
}
CONTENT = {  # target -> (file name pattern, what must be inside)
    "Containers and orchestration": (r"(?i)\.ya?ml$", r"(?m)^kind:\s*(Deployment|StatefulSet|DaemonSet|CronJob|Ingress)\b"),
    "Serverless": (r"(?i)(^|/)template\.(ya?ml|json)$", r"AWS::Serverless"),
    "Infrastructure as code": (r"(?i)(^|/)(template|cloudformation[^/]*)\.(ya?ml|json)$", r"AWSTemplateFormatVersion"),
}
TEXT = {
    "Containers and orchestration": r"(?i)\b(docker|podman|kubectl|helm)\s+[\w-]+|\bkubernetes\b|\boci image",
    "Cloud application services": r"(?i)\b(aws|az|gcloud)\s+[a-z][\w-]*(\s+[a-z][\w-]*)?|\b(elastic beanstalk|app service|cloud run|app engine|fargate)\b",
    "Serverless": r"(?i)\b(sam (deploy|build)|serverless deploy|sls deploy|aws lambda|func azure functionapp)\b|\blambda function\b|\bcloud functions\b",
    "Virtual machines and data centers": r"(?i)\b(ansible-playbook|packer build|systemctl|rsync)\b|\bvirtual machines?\b|\bon-?prem",
    "Web and mobile applications": r"(?i)\b(fastlane|testflight|play store|app store|firebase (deploy|app distribution)|netlify deploy|vercel deploy|gradlew|xcodebuild)\b|\bstatic site\b",
    "Data and database changes": r"(?i)\b(alembic (upgrade|downgrade)|flyway migrate|liquibase update|prisma migrate|dbt (run|build))\b|\bschema migrations?\b|\bdatabase migrations?\b",
    "Infrastructure as code": r"(?i)\b(terraform|tofu|pulumi (up|preview)|cdk (deploy|diff)|aws cloudformation)\b",
}
IMAGE = re.compile(r"^[\w.-]+(:\d+)?/[\w./-]+(:[\w.-]+|@sha256:[0-9a-f]{64})$|^[\w./-]+@sha256:[0-9a-f]{64}$")
ARTIFACT_EXT = {"Web and mobile applications": (".apk", ".aab", ".ipa"), "Virtual machines and data centers": (".ova", ".vmdk", ".ami", ".rpm", ".deb")}
UNSUPPORTED = {  # technology -> (file pattern, text pattern)
    "Mainframe (JCL, COBOL)": (r"(?i)\.(jcl|cbl|cob|pli)$", r"(?i)\bjcl\b"),
    "Windows installers and SCCM": (r"(?i)\.(msi|wxs)$", r"(?i)\bsccm\b|\.msi\b"),
    "Cloud Foundry": (r"(?i)(^|/)manifest\.ya?ml$", r"(?i)\bcf push\b"),
    "HashiCorp Nomad": (r"(?i)\.nomad(\.hcl)?$", r"(?i)\bnomad job run\b"),
    "Salesforce": (r"(?i)(^|/)sfdx-project\.json$", r"(?i)\bsfdx\b"),
    "SAP transports": (r"(?i)\.abap$", r"(?i)\bsap transport\b"),
    "Heroku": (r"(?i)(^|/)(procfile|app\.json)$", r"(?i)\bheroku\b"),
}
SKIP = re.compile(r"(?i)(^|/)(\.git|node_modules|venv|\.venv|__pycache__|dist|build)/")


def repo_files(repo, limit=4000):
    if not repo:
        return []
    r = subprocess.run(["git", "-C", str(repo), "ls-files", "--cached", "--others", "--exclude-standard"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    names = r.stdout.splitlines() if r.returncode == 0 else [str(p.relative_to(repo)) for p in pathlib.Path(repo).rglob("*") if p.is_file()]
    return [n for n in names if not SKIP.search(n)][:limit]


def head(repo, name):
    try:
        return (pathlib.Path(repo) / name).read_text(errors="ignore")[:4000]
    except OSError:
        return ""


def detect(repo, artifact="", texts=()):
    files, blob = repo_files(repo), "\n".join(texts)
    ev = {t: [] for t in CHECKS}
    for t, rx in FILES.items():
        ev[t] += [f for f in files if re.search(rx, f)]
    for t, (name_rx, body_rx) in CONTENT.items():
        ev[t] += [f"{f} (contents)" for f in files if re.search(name_rx, f) and re.search(body_rx, head(repo, f))]
    for t, rx in TEXT.items():
        hits = sorted({m.group(0).strip().lower() for m in re.finditer(rx, blob)})[:4]
        if hits:
            ev[t].append("the release documents or plan mention: " + ", ".join(hits))
    art = (artifact or "").strip().strip("`")
    if IMAGE.match(art):
        ev["Containers and orchestration"].append(f"the artifact '{art}' is an image reference")
    for t, exts in ARTIFACT_EXT.items():
        if art.lower().endswith(exts):
            ev[t].append(f"the artifact '{art}' is a {art.rsplit('.', 1)[-1]} package")
    ev["Cross-cutting delivery systems"] = ev["Cross-cutting delivery systems"] or ["always considered: approval, immutability, credentials and audit apply to every release"]
    targets = [dict(target=t, checks=CHECKS[t], evidence=list(dict.fromkeys(e))[:5]) for t, e in ev.items() if e]
    un = []
    for what, (frx, trx) in UNSUPPORTED.items():
        hit = [f for f in files if re.search(frx, f)] + (["a mention in the release documents or plan"] if re.search(trx, blob) else [])
        if what == "Cloud Foundry":  # a bare manifest.yml is common: only a cloud foundry manifest names applications
            hit = [f for f in hit if f.startswith("a mention") or "applications:" in head(repo, f)]
        if what == "Heroku":
            hit = [f for f in hit if f.startswith("a mention") or "heroku" in head(repo, f).lower() or f.lower().endswith("procfile")]
        if hit:
            un.append(dict(what=what, why=f"no release adapter ({', '.join(hit[:3])}): the checks for it need a specialist; nothing was assumed about how it deploys"))
    return dict(targets=targets, unsupported=un)


def required(det):
    """(target, check) pairs the plan must say how it covers."""
    return [(t["target"], c) for t in det["targets"] for c in t["checks"]]


def render(det, status=None):
    """status: {(target, check): 'Addressed' | 'Not covered' | 'Not applicable' | 'Not in the plan'} once there is a plan, else None."""
    rows = "\n".join(f"| {t['target']} | {'; '.join(t['evidence'])} |" for t in det["targets"])
    out = "## Release targets (detected by code from repository, artifact and environment evidence)\n| Target | Evidence |\n|---|---|\n" + rows + "\n"
    if status is not None:
        out += "\n## Release checks\n| Target | Check | Status |\n|---|---|---|\n" + "\n".join(f"| {t} | {c} | {status.get((t, c), 'Not in the plan')} |" for t, c in required(det)) + "\n"
    out += "\n## Unsupported targets (routed for specialist review)\n" + ("\n".join(f"- **{u['what']}**: {u['why']}" for u in det["unsupported"]) or "None found.") + "\n"
    return out


def prompt_note(det):
    note = "\nDeployment targets detected by code (the plan's 'Target checks' table needs one row for every check listed):\n"
    note += "".join(f"- {t['target']}: {'; '.join(t['checks'])}\n" for t in det["targets"])
    if det["unsupported"]:
        note += "Unsupported here (do NOT plan how to deploy these; say they need a specialist): " + ", ".join(u["what"] for u in det["unsupported"]) + "\n"
    return note
